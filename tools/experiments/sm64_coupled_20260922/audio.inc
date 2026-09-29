// Functional voice lifetimes during fast warm-up; real mixer RTL after handoff.
// OS service instruction costs are a configurable approximation. The app's
// sequence engine and sample decoder execute as normal RISC-V instructions.
struct Voice {
    uint32_t reg[12] = {};
    uint64_t position = 0;
    int priority = 0;
};
static Voice voices[32];
static uint32_t voice_mask, ended_mask;
static uint64_t warmup_audio_time;

static void warmup_advance(uint64_t now) {
    uint64_t dt = now - warmup_audio_time;
    warmup_audio_time = now;
    for (unsigned i=0;i<31;i++) if (voice_mask & (1u<<i)) {
        auto &v=voices[i];
        v.position += dt * v.reg[2] * 48000 / 1000000;
        uint64_t end = uint64_t((v.reg[3]&4) ? v.reg[7] : v.reg[1]) << 16;
        if (v.position >= end) {
            uint64_t start=uint64_t(v.reg[8])<<16;
            if ((v.reg[3]&4) && end>start) v.position=start+(v.position-start)%(end-start);
            else { voice_mask &= ~(1u<<i); ended_mask |= 1u<<i; }
        }
        if (dt>=1000) v.reg[6]=v.reg[9];
    }
}
static void mix_write(unsigned voice, unsigned field, uint32_t value) {
    assert(voice<32 && field<12);
    voices[voice].reg[field]=value;
    if (!tb) return;
    if (active) coupled_sync();
    tb->mix_sel=voice; tb->mix_field=field; tb->mix_data=value; tb->eval();
    unsigned waited=0;
    while (!tb->mix_ready) { tick(); if (++waited>100000) abort(); }
    tb->mix_wr=1; tick(); tb->mix_wr=0;
    if (active) env->cpu->model->cyc += waited+1;
}
static void mix_clear_irq(uint32_t mask) {
    if (!tb) return;
    if (active) coupled_sync();
    tb->mix_irq_clear_wr=1; tb->mix_irq_clear=mask; tick(); tb->mix_irq_clear_wr=0;
    if (active) env->cpu->model->cyc++;
}
static void transfer_voices() {
    for(unsigned i=0;i<32;i++) {
        uint32_t ctrl=voices[i].reg[3];
        mix_write(i,3,0);
        for(unsigned f=0;f<12;f++) if(f!=3 && f!=4 && f!=5) mix_write(i,f,voices[i].reg[f]);
        mix_write(i,4,voices[i].position>>16);
        mix_write(i,5,voices[i].position&65535);
        if(!(voice_mask&(1u<<i))) ctrl=0;
        mix_write(i,3,ctrl);
    }
    mix_clear_irq(~0u);
}
extern "C" void coupled_enter(uint32_t pc) {
    if (!active) return;
    coupled_sync();
    if (pc == coupled_render_pc) {
        event("render_start",0,env->buf_draw);
    } else if (pc == coupled_audio_pc && sound_enabled) {
        audio_ticks++;
        fprintf(audio_events,"tick,%llu,-1,0,0,0\n",(unsigned long long)cycles);
    }
}
extern "C" int coupled_audio_service(void *p, int svc, uint32_t *result) {
    if (!getenv("COUPLED_SOUND")) return 0;
    if (!(svc==18 || svc==19 || svc==20 || svc==21 || svc==24 || svc==26 ||
          svc==34 || svc==35 || svc==36 || svc==56 || svc==57 || svc==58)) return 0;
    auto E=static_cast<qenv *>(p);
    uint32_t *x=E->cpu->x, a=x[10], b=x[11], c=x[12], d=x[13];
    if (!active) warmup_advance(E->vt_us);
    else {
        unsigned cost=getenv("COUPLED_MIXER_SERVICE_CYCLES") ? atoi(getenv("COUPLED_MIXER_SERVICE_CYCLES")) : 100;
        E->cpu->model->cyc+=cost;
        coupled_sync();
    }
    auto reap=[&]() {
        uint32_t ended=active ? tb->mix_ended : ended_mask;
        voice_mask &= ~ended;
        ended_mask |= ended;
        if(active) mix_clear_irq(ended);
    };
    *result=0;
    switch(svc) {
    case 18:
        voice_mask=ended_mask=0;
        for(unsigned i=0;i<32;i++) { voices[i]=Voice{}; mix_write(i,3,0); }
        break;
    case 19: {
        assert(x[14]==0); // SM64 starts silent, then writes its exact stereo target.
        reap();
        int v=-1;
        for(int i=0;i<31;i++) if(!(voice_mask&(1u<<i))) {v=i;break;}
        if(v<0) {int lowest=(int)d;for(int i=0;i<31;i++) if(voices[i].priority<lowest) {lowest=voices[i].priority;v=i;}}
        if(v<0 || !a || !b) {*result=~0u;break;}
        mix_write(v,3,0); mix_clear_irq(1u<<v); ended_mask &= ~(1u<<v);
        voices[v].position=0; voices[v].priority=(int)d;
        mix_write(v,0,a&0x1fffffff); mix_write(v,1,b); mix_write(v,2,(uint64_t(c)<<16)/48000);
        mix_write(v,4,0); mix_write(v,8,0); mix_write(v,7,b);
        mix_write(v,6,0); mix_write(v,10,8); mix_write(v,9,0);
        mix_write(v,3,1); voice_mask|=1u<<v; *result=v;
        break;
    }
    case 20:
        if(a<32) {mix_write(a,3,0); voice_mask&=~(1u<<a);}
        break;
    case 21:
        for(unsigned i=0;i<32;i++) mix_write(i,3,0);
        voice_mask=0; break;
    case 24: *result=a<32 && (voice_mask&(1u<<a)); break;
    case 26:
        if(a<32) {
            if((int)b<0) mix_write(a,3,voices[a].reg[3]&~4u);
            else {mix_write(a,8,b); if(c)mix_write(a,7,c); mix_write(a,3,voices[a].reg[3]|4);}
        }
        break;
    case 34:
        if(a<32) {
            mix_write(a,2,b);
            uint32_t volume=(c&255)|((d&255)<<8);
            if(voices[a].reg[9]!=volume) mix_write(a,9,volume);
            if(active) {voice_commits++; fprintf(audio_events,"commit,%llu,%u,%u,%u,%u\n",(unsigned long long)cycles,a,b,c,d);}
        }
        break;
    case 35: if(a<32)mix_write(a,10,b&255); break;
    case 36: reap(); *result=ended_mask; ended_mask=0; break;
    case 56: break; // all group gains are 255 in this SM64 workload
    case 57: assert(b==255); break;
    case 58: assert(a==255); break;
    }
    return 1;
}
static void finish_wav() {
    uint32_t size=uint32_t(audio_samples*4);
    uint8_t h[44]={};
    auto put16=[&](int n,uint16_t v){memcpy(h+n,&v,2);};
    auto put32=[&](int n,uint32_t v){memcpy(h+n,&v,4);};
    memcpy(h,"RIFF",4); put32(4,size+36); memcpy(h+8,"WAVEfmt ",8);
    put32(16,16); put16(20,1); put16(22,2); put32(24,48000); put32(28,192000);
    put16(32,4); put16(34,16); memcpy(h+36,"data",4); put32(40,size);
    fseek(wav,0,SEEK_SET); fwrite(h,1,44,wav); fflush(wav);
}
