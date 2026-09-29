#include "ideal_memory.h"
#include <vector>
#include <cstdio>
int main() {
    for(unsigned latency: {1u,4u,16u}) {
        std::vector<uint8_t> memory(1u<<26,0x5a);IdealMemory m;m.latency=latency;
        auto cycle=[&](unsigned now,IdealMemory::Input i) {
            auto o=m.output(now,memory.data());m.edge(now,i,o,memory.data());return o;
        };
        IdealMemory::Input i;i.aw=true;i.wa=0x1000003c;i.wl=2;cycle(0,i);
        i={};i.w=true;i.mask=5;i.data=0x12345678;i.aw=true;i.wa=0x10000080;i.wl=1;cycle(1,i);
        i={};i.w=true;i.mask=0;i.data=0xffffffff;cycle(2,i);
        i={};i.w=true;i.mask=15;i.data=0x87654321;i.last=true;cycle(3,i);
        i.last=false;i.data=0x01020304;cycle(4,i);
        i.last=true;i.mask=10;i.data=0xabcdef12;cycle(5,i);
        for(unsigned n=6;n<32;n++)cycle(n,{});
        assert(m.idle()&&m.replies==2&&m.write_beats==5);
        const uint32_t expected[3]={0x5a345a78,0x5a5a5a5a,0x87654321};
        i={};i.ar=true;i.ra=0x1000003c;i.rl=2;cycle(32,i);
        unsigned beats=0;
        for(unsigned n=33;n<64;n++) {
            auto o=cycle(n,{});
            assert(o.rvalid==(n>=32+latency&&n<35+latency));
            if(o.rvalid){assert(o.data==expected[beats]);assert(o.rlast==(beats==2));beats++;}
        }
        uint32_t a,b;memcpy(&a,memory.data()+0x80,4);memcpy(&b,memory.data()+0x84,4);
        assert(a==0x01020304&&b==0xab5aef5a&&beats==3&&m.idle());
        assert(memory[0x3b]==0x5a&&memory[0x48]==0x5a);
    }
    puts("PASS: masks, crossing burst, queued AW/B order, read beats and latency 1/4/16");
}
