// Byte-exact write-back oracle: aliases, byte masks, stalls, drains and aborts.
#include "Vwc_protocol.h"
#include "verilated.h"
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <random>
#include <unordered_map>

static Vwc_protocol d;
static std::unordered_map<uint32_t, uint32_t> actual, expected;
static uint64_t cycles=0, accepted=0, emitted=0;
static bool was_stalled=false;
static uint32_t held_addr, held_data, held_strb;
static void require(bool ok, const char* why) {
    if (!ok) { std::fprintf(stderr,"FAIL cycle %llu: %s\n", (unsigned long long)cycles, why); std::exit(1); }
}
static void write(std::unordered_map<uint32_t,uint32_t>& mem, uint32_t addr, uint32_t data, unsigned mask) {
    uint32_t value=mem[addr];
    for(unsigned lane=0;lane<4;lane++) if(mask&(1u<<lane)) {
        uint32_t bits=255u<<(lane*8); value=(value&~bits)|(data&bits);
    }
    mem[addr]=value;
}
static bool tick() {
    d.clk=0; d.eval();
    bool live=d.reset_n&&!d.soft_reset;
    if(was_stalled&&live) require(d.wc_output_valid && d.wc_output_addr==held_addr
        && d.wc_output_data==held_data && d.wc_output_strb==held_strb,"output changed under backpressure");
    was_stalled=live&&d.wc_output_valid&&!d.fbwq_stage_can_load;
    held_addr=d.wc_output_addr;held_data=d.wc_output_data;held_strb=d.wc_output_strb;
    bool take=live&&d.fbwq_req_valid&&d.wc_input_ready;
    if(take) { write(expected,d.fbwq_req_addr,d.fbwq_req_data,d.fbwq_req_strb);accepted++; }
    if(live&&d.wc_output_valid&&d.fbwq_stage_can_load) {
        require((d.wc_output_addr&3)==0 && d.wc_output_strb!=0,"invalid output address or mask");
        write(actual,d.wc_output_addr,d.wc_output_data,d.wc_output_strb);emitted++;
    }
    d.clk=1;d.eval();cycles++;
    return take;
}
static void compare() {
    for(const auto& [addr,value]:expected) require(actual[addr]==value,"memory differs after drain");
    for(const auto& [addr,value]:actual) require(expected[addr]==value,"unexpected output write");
}
static void drain(std::mt19937& rng, bool pulse=false) {
    d.fbwq_req_valid=0; d.wc_flush=!pulse;d.tex_flush_req=pulse;
    for(unsigned n=0;;n++) {
        require(n<100000,"drain timeout");
        d.fbwq_stage_can_load=(rng()%5)==0;
        tick();d.tex_flush_req=0;
        if(!d.wc_busy)break;
    }
    d.wc_flush=0;compare();
}
static void send(std::mt19937& rng,uint32_t addr,uint32_t data,unsigned mask,bool cacheable) {
    d.fbwq_req_valid=1;d.fbwq_req_addr=addr;d.fbwq_req_data=data;
    d.fbwq_req_strb=mask;d.fbwq_req_combine=cacheable;
    for(unsigned n=0;;n++) {
        require(n<100000,"input timeout");
        d.fbwq_stage_can_load=(rng()%4)==0;
        if(tick())break;
    }
    d.fbwq_req_valid=0;
}
static void reset(bool soft) {
    d.fbwq_req_valid=0;d.fbwq_stage_can_load=0;d.wc_flush=0;d.tex_flush_req=0;
    if(soft)d.soft_reset=1;else d.reset_n=0;
    tick();d.reset_n=1;d.soft_reset=0;
    // Abort discards buffered writes. Completed physical writes remain.
    expected=actual;
}
int main(int argc,char** argv) {
    Verilated::commandArgs(argc,argv);
    unsigned seed=std::strtoul(argv[argc-1],nullptr,10);std::mt19937 rng(seed);
    reset(false);
    // First request is held throughout RAM initialization.
    send(rng,0x100000,0x12345678,1,true);
    drain(rng);
    // Continuous byte updates to one entry require read-after-write forwarding.
    // Alternate colliding tags too, so every cycle can both evict and refill.
    uint32_t alias=0x100004;
    auto index=[](uint32_t addr) { uint32_t w=addr>>2;return (w^(w>>10)^(w>>18))&255; };
    while(index(alias)!=index(0x100000))alias+=4;
    for(unsigned mode=0;mode<2;mode++) {
        uint64_t start=cycles;
        for(unsigned n=0;n<1024;n++) {
            d.fbwq_req_valid=1;d.fbwq_req_combine=1;
            d.fbwq_req_addr=mode&&(n&1)?alias:0x100000;
            d.fbwq_req_data=rng();d.fbwq_req_strb=1u<<(n&3);
            d.fbwq_stage_can_load=1;
            unsigned waits=0;
            while(!tick())require(++waits<1000,"continuous stream timeout");
        }
        uint64_t used=cycles-start;
        std::printf("STREAM %s: 1024 writes in %llu cycles\n",mode?"aliases":"same-entry",(unsigned long long)used);
        if(Verilated::commandArgsPlusMatch("wc_pipelined")[0])
            require(used==1024,"merge pipeline failed to accept one write per cycle");
        drain(rng,true);
    }
    uint64_t old_emitted=emitted;
    for(unsigned lane=0;lane<4;lane++) for(unsigned y=0;y<200;y++)
        send(rng,0x100000+320*y,0x11223344u*(lane+1),1u<<lane,true);
    drain(rng,true);
    require(emitted-old_emitted==200,"strided writes did not combine to one word per row");
    // Pending inputs must still drain while a level barrier stays asserted.
    d.wc_flush=1;
    send(rng,0x1200,0xabcdef,5,true);
    send(rng,0x1300,0x123456,15,false);
    drain(rng);
    for(unsigned batch=0;batch<500;batch++) {
        for(unsigned n=0;n<1000;n++) {
            uint32_t addr;
            switch(rng()%5) {
                case 0:addr=0x100000+(rng()%200)*320;break;
                case 1:addr=0x100000+(rng()%256)*4;break;
                case 2:addr=0x100000+(rng()%4)*1024;break;
                case 3:addr=(rng()&0xfffffc);break;
                default:addr=(rng()&0x3fffffc);break;
            }
            send(rng,addr,rng(),rng()%16,(rng()%32)!=0);
            if((rng()%1000)==0) { reset(true); }
            if((rng()%8)==0) { d.fbwq_stage_can_load=0;tick(); }
        }
        drain(rng,(batch%2)==0);
    }
    // Abort during lookup, flush and held output at varying cycle offsets.
    for(unsigned n=0;n<512;n++) {
        send(rng,0x100000+(n%200)*320,rng(),3,true);
        d.fbwq_stage_can_load=0;d.wc_flush=1;
        for(unsigned k=0;k<(n%19);k++)tick();
        reset(n%2);send(rng,0x100000,rng(),15,false);drain(rng,true);
    }
    std::printf("PASS seed %u: %llu accepted, %llu emitted, %llu cycles; byte oracle, stalls, reset and flush\n",
        seed,(unsigned long long)accepted,(unsigned long long)emitted,(unsigned long long)cycles);
}
