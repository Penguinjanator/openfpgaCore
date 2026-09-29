// Optimistic GPU-only AXI responder. Physical scanout/audio keep their SDRAM path.
// One read burst at a time; independent read/write channels, one 32-bit beat/cycle.
#pragma once
#include <cassert>
#include <cstdint>
#include <cstring>
#include <deque>
struct IdealMemory {
    struct Input { bool ar=false,aw=false,w=false,last=false; uint32_t ra=0,wa=0,data=0; unsigned rl=0,wl=0,mask=0; };
    struct Output { bool arready=false,awready=false,wready=false,rvalid=false,rlast=false,bvalid=false; uint32_t data=0; };
    struct Write { uint32_t address; unsigned left; };
    std::deque<Write> writes;
    std::deque<uint64_t> responses;
    unsigned latency=1, read_left=0;
    uint32_t read_address=0;
    uint64_t read_due=0, reads=0, read_beats=0, write_requests=0, write_beats=0, replies=0;
    static uint32_t offset(uint32_t address) {assert(!(address&3));return address&0x03ffffffu;}
    Output output(uint64_t now,const uint8_t *memory) const {
        Output o;o.arready=read_left==0;o.awready=writes.size()+responses.size()<16;
        o.wready=!writes.empty();o.bvalid=!responses.empty()&&responses.front()<=now;
        if(read_left&&now>=read_due) {
            o.rvalid=true;o.rlast=read_left==1;std::memcpy(&o.data,memory+offset(read_address),4);
        }
        return o;
    }
    void edge(uint64_t now,const Input& i,const Output& o,uint8_t *memory) {
        if(o.bvalid){responses.pop_front();replies++;}
        if(o.rvalid){assert(read_left);read_left--;read_address+=4;read_beats++;}
        if(i.w&&o.wready) {
            auto &w=writes.front();assert(i.last==(w.left==1));
            uint32_t a=offset(w.address);
            for(unsigned b=0;b<4;b++)if(i.mask&(1u<<b))memory[a+b]=i.data>>(8*b);
            w.address+=4;w.left--;write_beats++;
            if(!w.left){writes.pop_front();responses.push_back(now+latency);}
        }
        if(i.ar&&o.arready){assert(!read_left);read_address=i.ra;read_left=i.rl+1;read_due=now+latency;reads++;}
        if(i.aw&&o.awready){writes.push_back({i.wa,i.wl+1});write_requests++;}
    }
    bool idle()const{return !read_left&&writes.empty()&&responses.empty();}
};
