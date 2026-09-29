// Execute the new DMA state machine against the real Pocket SDRAM stack.
// Compare every decoded word, including commands split across DMA bursts.
#include <cassert>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <deque>
#include <vector>
#include "Vtb_gpu_transluc.h"
#include "Vtb_gpu_transluc___024root.h"

struct Bench {
    Vtb_gpu_transluc t;
    std::deque<uint32_t> expected;
    uint64_t cycles=0, decoded=0, fetched=0, credits=0, payload_waits=0;
    bool checking=false;
    void tick() {
        t.clk=0;t.eval();
        auto r=t.rootp;
        if(checking) {
            auto state=r->tb_gpu_transluc__DOT__gpu__DOT__state;
            if(state==1 || state==3) {
                assert(!expected.empty());
                auto word=r->tb_gpu_transluc__DOT__gpu__DOT__ring_rd_data;
                if(word!=expected.front()) {
                    fprintf(stderr,"decode mismatch at %llu: %08x != %08x\n",
                            (unsigned long long)decoded,word,expected.front());
                    abort();
                }
                expected.pop_front(); decoded++;
            }
            fetched+=t.trace_dma_write;
            credits+=t.trace_dma_credit_wait;
            payload_waits+=t.trace_dma_payload_wait;
        }
        t.clk=1;t.eval();cycles++;
        assert(!t.dbg_mem_errors);
    }
    void write(unsigned r,uint32_t v) { t.reg_addr=r;t.reg_wdata=v;t.reg_wr=1;tick();t.reg_wr=0; }
    uint32_t read(unsigned r) {t.reg_addr=r;t.eval();return t.reg_rdata;}
    Bench() {
        t.aggr_en=1;t.m1_rready=t.m2_rready=t.m3_rready=1;
        t.reset_n=0;for(int i=0;i<20;i++)tick();
        t.reset_n=1;for(int i=0;i<30000;i++)tick();
        write(0,4);write(0,1);for(int i=0;i<10;i++)tick();
        checking=true;
    }
    void submit(const std::vector<uint32_t>& words,uint32_t offset,bool stream) {
        auto memory=reinterpret_cast<uint8_t*>(&t.rootp->tb_gpu_transluc__DOT__sdram_chip__DOT__mem[0]);
        memcpy(memory+offset,words.data(),words.size()*4);
        for(auto word:words)expected.push_back(word);
        while(read(5)&64)tick();
        write(3,offset);write(7,(stream?0x80000000u:0u)|words.size());write(11,1);
    }
    void finish(uint32_t token) {
        auto limit=cycles+10000000;
        while(t.fence_reached!=token || t.busy) {tick();assert(cycles<limit);}
        assert(expected.empty());
        assert(!(read(5)&0x200));
    }
};

std::vector<uint32_t> list(unsigned count,uint32_t token,bool flip=false) {
    std::vector<uint32_t> words;
    if(flip) words={0x42000002,1,token-1};
    unsigned serial=0;
    while(words.size()+2<count) {
        unsigned payload=(serial*17)%50;
        if(words.size()+1+payload+2>count)payload=0;
        words.push_back(payload); // opcode 0: drain arbitrary payload
        for(unsigned i=0;i<payload;i++)words.push_back(0xdead0000u+(serial<<6)+i);
        serial++;
    }
    words.push_back(0x02000001);words.push_back(token);
    assert(words.size()==count);
    return words;
}

int main() {
    {
        Bench b;auto words=list(1931,100);
        b.submit(words,0x1000000,false);b.finish(100);
        assert(b.decoded==words.size() && b.fetched==words.size());
        printf("PASS legacy DMA: %llu words\n",(unsigned long long)b.decoded);
    }
    {
        Bench b;auto words=list(65535,200,true);b.t.slave_swap_pending=1;
        b.submit(words,0x1000000,true);
        for(unsigned i=0;i<100000;i++)b.tick();
        assert(b.fetched<4110 && b.fetched>4000 && b.credits>1000);
        b.t.slave_swap_pending=0;b.finish(200);
        assert(b.decoded==words.size() && b.fetched==words.size() && b.payload_waits>0);
        printf("PASS maximum list, blocked flip, ring wrap, partial payloads: %llu words, %llu credit cycles, %llu payload cycles\n",
            (unsigned long long)b.decoded,(unsigned long long)b.credits,(unsigned long long)b.payload_waits);
    }
    {
        Bench b;
        b.submit(list(8193,300),0x1000000,true);
        b.submit(list(8194,301),0x1100000,true);
        b.submit(list(8195,302),0x1200000,true);
        b.finish(302);
        assert(b.decoded==24582 && b.fetched==24582);
        // A legacy descriptor after streamed traffic still publishes atomically.
        b.submit(list(777,303),0x1300000,false);b.finish(303);
        assert(b.decoded==25359 && b.fetched==25359);
        printf("PASS queued descriptors and stream-to-legacy transition: %llu words\n",(unsigned long long)b.decoded);
    }
}
