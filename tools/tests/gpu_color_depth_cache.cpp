// Experimental cache scoreboard: masked writes, fill merging, conflict eviction,
// bypass/cross-range bursts, maintenance, reset, and randomized memory stalls.
// Memory models the Pocket arbiter: W beats enter an 8-word posted queue,
// commit in order at random times, B returns per burst on commit, and reads
// see committed memory only, so a read may overtake a queued write.
#include "Vgpu_color_depth_cache.h"
#include "verilated.h"
#ifndef CACHE_ALL_MODEL
#define CACHE_ALL_MODEL 0
#endif
#define LINE_MODEL (4u<<WORD_BITS_MODEL)
#define WORDS_PER_LINE (1u<<WORD_BITS_MODEL)
#define SETS_MODEL (1u<<SET_BITS_MODEL)
#ifdef HAS_BUS_RESET
#define SET_BUS_RESET(v) (t.bus_reset_n=(v))
#else
#define SET_BUS_RESET(v) ((void)0)
#endif
#include <array>
#include <deque>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <stdexcept>
#include <string>
#include <vector>

static void check(bool ok, const char *s) { if (!ok) throw std::runtime_error(s); }
struct Result { bool ar, aw, w, r, last, b; uint32_t data; };
struct Beat { uint32_t addr, data; unsigned strb; bool last; };
struct Test {
    Vgpu_color_depth_cache t;
    std::array<uint32_t,16384> mem{}, expected{};
    uint32_t rng=1, ra=0, wa=0;
    unsigned rn=0, wn=0, bd=0, b_ready=0, commit_hold=0;
    std::deque<Beat> wq;   // posted, uncommitted write beats
    uint32_t input_write_addr=0;
    unsigned input_write_words=0;
    uint64_t cycles=0, reads=0, writes=0;
    bool ar_stalled=false, aw_stalled=false, w_stalled=false;
    uint64_t held_ar=0, held_aw=0, held_w=0;
    uint32_t random() { rng^=rng<<13; rng^=rng>>17; rng^=rng<<5; return rng; }
    Result tick() {
        check(++cycles<50000000,"timeout");
        t.m_arready=!rn && (random()%4!=0);
        // Arbiter posting: bursts up to 8 beats need queue space; longer
        // (bypass) bursts are accepted only into an empty queue.
        unsigned aw_beats=unsigned(t.m_awlen)+1;
        t.m_awready=!wn && (aw_beats<=8 ? wq.size()+aw_beats<=8 : wq.empty()) && (random()%4!=0);
        t.m_wready=wn && (random()%3!=0);
        t.m_rvalid=rn && (random()%3!=0);
        t.m_rdata=rn ? mem.at(ra/4) : 0;
        t.m_rlast=rn==1;
        t.m_bvalid=b_ready && bd==1;
        t.clk=0; t.eval();
        uint64_t ar=(uint64_t(t.m_araddr)<<8)|t.m_arlen;
        uint64_t aw=(uint64_t(t.m_awaddr)<<8)|t.m_awlen;
        uint64_t w=(uint64_t(t.m_wdata)<<5)|(t.m_wstrb<<1)|t.m_wlast;
        if(t.reset_n) {
            check(!ar_stalled || (t.m_arvalid && ar==held_ar),"AR changed under backpressure");
            check(!aw_stalled || (t.m_awvalid && aw==held_aw),"AW changed under backpressure");
            check(!w_stalled || (t.m_wvalid && w==held_w),"W changed under backpressure");
        }
        ar_stalled=t.reset_n && t.m_arvalid && !t.m_arready; held_ar=ar;
        aw_stalled=t.reset_n && t.m_awvalid && !t.m_awready; held_aw=aw;
        w_stalled=t.reset_n && t.m_wvalid && !t.m_wready; held_w=w;
        Result result{bool(t.s_arvalid&&t.s_arready),bool(t.s_awvalid&&t.s_awready),
                      bool(t.s_wvalid&&t.s_wready),bool(t.s_rvalid),bool(t.s_rlast),
                      bool(t.s_bvalid),t.s_rdata};
        if (t.m_rvalid) { ra+=4; --rn; }
        if (t.m_bvalid) --b_ready;
        if (bd) --bd;
        if (b_ready && !bd && !t.m_bvalid) bd=1+random()%4;
        // Like the arbiter, reads go first: the queue head commits only with no
        // read in flight, after random holds (other masters), and its WLAST
        // beat releases a B.  Queued writes therefore linger behind fills.
        if (commit_hold) --commit_hold;
        else if (!wq.empty() && !rn) {
            commit_hold=random()%8==0 ? random()%48 : random()%3;
            Beat h=wq.front(); wq.pop_front();
            auto &v=mem.at(h.addr/4);
            for (unsigned b=0;b<4;b++) if (h.strb&(1<<b))
                v=(v&~(255u<<(b*8)))|(h.data&(255u<<(b*8)));
            if (h.last) ++b_ready;
        }
        if (t.m_arvalid && t.m_arready) {
            check(!rn,"overlapping memory reads"); ra=t.m_araddr; rn=t.m_arlen+1; ++reads;
        }
        if (t.m_awvalid && t.m_awready) {
            check(t.m_awlen<8 || (t.m_awaddr==input_write_addr &&
                  unsigned(t.m_awlen)+1==input_write_words),
                  "generated write burst exceeds Pocket arbiter capacity");
            check(!wn,"overlapping memory writes"); wa=t.m_awaddr; wn=t.m_awlen+1; ++writes;
        }
        if (t.m_wvalid && t.m_wready) {
            check(wn && bool(t.m_wlast)==(wn==1),"downstream WLAST/length mismatch");
            wq.push_back(Beat{wa,t.m_wdata,unsigned(t.m_wstrb),wn==1});
            wa+=4; --wn;
        }
        t.clk=1; t.eval();
        check(!t.protocol_error,"cache protocol_error");
        return result;
    }
    void reset() {
        t.s_arvalid=t.s_awvalid=t.s_wvalid=t.flush_req=t.write_no_allocate=0;
        // A bus reset also clears the arbiter: queued writes are lost.
        t.reset_n=0; SET_BUS_RESET(0); rn=wn=bd=b_ready=0; wq.clear();
        tick(); tick(); t.reset_n=1; SET_BUS_RESET(1);
        while(t.busy) tick();
        expected=mem;
    }
    // GPU soft reset: the cache FSM resets but writes already posted downstream
    // still commit and return B.  A bypass write issued at once must not take
    // an earlier writeback's B as its own, and the cache stays busy until all
    // posted writes have completed.  Dirty data still in the cache is lost.
    void soft_reset_then_bypass() {
        t.s_arvalid=t.s_awvalid=t.s_wvalid=t.flush_req=t.write_no_allocate=0;
        t.reset_n=0; tick(); tick(); t.reset_n=1;
        unsigned a=0x1000+(random()%64)*4, n=1+random()%8;
        // Full strobes: bytes around a partial write would inherit dirty data
        // the reset legitimately discarded.
        t.write_no_allocate=1; write(a,n,15); t.write_no_allocate=0;
        std::vector<uint32_t> mine(expected.begin()+a/4,expected.begin()+a/4+n);
        while(t.busy) tick();
        check(wq.empty() && !b_ready && !wn,"cache idle with posted writes outstanding");
        for(unsigned i=0;i<n;i++) check(mem.at(a/4+i)==mine[i],"bypass write after soft reset lost");
        expected=mem;
    }
    bool in_range(uint32_t a) const {
        return (a>=t.range0_lo && a<t.range0_hi) || (a>=t.range1_lo && a<t.range1_hi);
    }
    void write(uint32_t a,unsigned n,int fixed_mask=-1,bool contend=false) {
        input_write_addr=a; input_write_words=n;
        // Whole-burst bypass decisions mirror the cache's IDLE state; its B
        // must mean every beat committed (not an earlier writeback's B).
        bool touches=CACHE_ALL_MODEL;
        for(unsigned i=0;i<n && !touches;i++) touches=in_range(a+i*4);
        bool bypass=!touches || (!t.has_lines && (t.write_no_allocate || n>=8));
        if(contend) { t.s_araddr=a; t.s_arlen=0; t.s_arvalid=1; }
        t.s_awaddr=a; t.s_awlen=n-1; t.s_awvalid=1;
        for(;;) {
            auto r=tick(); check(!r.ar,"AR accepted while AW has priority");
            if(r.aw) break;
        }
        t.s_arvalid=0;
        t.s_awvalid=0;
        for (unsigned i=0;i<n;i++) {
            for(unsigned gap=random()%4;gap;gap--) tick();
            t.s_wdata=random(); t.s_wstrb=fixed_mask<0 ? random()&15 : fixed_mask;
            t.s_wlast=i+1==n; t.s_wvalid=1;
            while(!tick().w) {}
            auto &v=expected.at(a/4+i);
            for(unsigned b=0;b<4;b++) if(t.s_wstrb&(1<<b))
                v=(v&~(255u<<(b*8)))|(t.s_wdata&(255u<<(b*8)));
            t.s_wvalid=0;
        }
        while(!tick().b) {}
        // Bursts longer than a line are not posted: their B means committed.
        // Shorter ones are posted; later reads and flushes prove their order.
        if(bypass && n>WORDS_PER_LINE) for(unsigned i=0;i<n;i++)
            check(mem.at(a/4+i)==expected.at(a/4+i),"long bypass write completed before its beats committed");
        input_write_words=0;
    }
    void read(uint32_t a,unsigned n) {
        t.s_araddr=a; t.s_arlen=n-1; t.s_arvalid=1;
        while(!tick().ar) {}
        t.s_arvalid=0;
        for (unsigned i=0;i<n;) {
            auto r=tick(); if(!r.r) continue;
            if(r.data!=expected.at(a/4+i)) {
                fprintf(stderr,"read %08x got %08x expected %08x cycle %llu\n",a+i*4,r.data,
                        expected.at(a/4+i),(unsigned long long)cycles);
                throw std::runtime_error("read scoreboard mismatch");
            }
            check(r.last==(i+1==n),"upstream RLAST mismatch"); ++i;
        }
    }
    void flush() {
        t.flush_req=1; while(!t.flush_done) tick();
        check(!t.has_lines && !t.busy,"maintenance left live cache lines");
        check(wq.empty() && !b_ready,"flush_done with posted writes outstanding");
        check(mem==expected,"flush memory mismatch");
        for(unsigned i=0;i<8;i++) { tick(); check(t.flush_done,"flush_done not held"); }
        t.flush_req=0; tick();
    }
    void run() {
        t.range0_lo=0x1000; t.range0_hi=0x5000;
        t.range1_lo=0x8000; t.range1_hi=0xc000;
        for(auto &w:mem) w=random(); reset();
        t.write_no_allocate=1;
        write(0x1000,1,3); write(0x1004,8,15);
        check(!t.has_lines,"no-allocation hint allocated an empty cache");
        read(0x1000,16); write(0x1004,1,12); read(0x1000,16);
        flush(); t.write_no_allocate=0;
        // Read ownership must merge the untouched bytes around partial writes.
        write(0x1000,8,15,true); read(0x1000,8);
        for(unsigned mask=0;mask<16;mask++) {
            write(0x1000+mask*16,1,mask); read(0x1000+mask*16,4);
        }
        // Every boundary, including whole-burst bypass and the maximum AXI length.
        for(auto a:{0xff0u,0x4ff0u,0x7ff0u,0xbff0u,0x100u,0x9000u}) {
            write(a,256); read(a,256);
        }
        // Posted bypass bursts (write_no_allocate into an empty cache) that
        // spill into the next line, read straight back from both lines: fills
        // must wait for the queued beats of either line.
        for(unsigned i=0;i<400;i++) {
            flush();
            uint32_t a=0x1000+(random()%(SETS_MODEL*4))*LINE_MODEL+(random()%WORDS_PER_LINE)*4;
            unsigned n=1+random()%WORDS_PER_LINE;
            t.write_no_allocate=1; write(a,n,15); t.write_no_allocate=0;
            read((a+(n-1)*4)&~(LINE_MODEL-1),WORDS_PER_LINE); read(a&~(LINE_MODEL-1),WORDS_PER_LINE);
        }
        flush();
        // Dirty a line, evict it with same-set reads, and read it straight back:
        // the refill must not overtake the victim's queued writeback.
        for(unsigned i=0;i<400;i++) {
            uint32_t base=0x1000+(random()%SETS_MODEL)*LINE_MODEL;
            write(base+(random()%4)*4,1+random()%3,15);
            for(unsigned w=1;w<=WAYS_MODEL;w++) read(base+w*LINE_MODEL*SETS_MODEL,1);
            read(base,4);
        }
        for(unsigned i=0;i<6000;i++) {
            unsigned n=1+random()%32; uint32_t a;
            if(i%3==0) a=0x1000+((random()%48)*256); // conflicting sets
            else if(i%3==1) a=0x8000+(random()%32)*4; // reuse hot partial lines
            else a=(random()%(16384-n))*4;
            if(random()&1) write(a,n); else read(a,n);
            if(i%211==0) {
                flush();
                // CPU mutation is legal after flush/invalidate; no stale hits.
                unsigned word=0x8000/4+random()%32;
                mem[word]=expected[word]=random(); read(word*4,1);
            }
        }
        flush();
        // Reprogram ranges only after maintenance.
        t.range0_lo=0; t.range0_hi=0x400; t.range1_lo=t.range1_hi=0;
        write(0,256); read(0,256); flush();
        // Reset intentionally discards pending dirty data.
        write(0,16,15); reset(); read(0,16); flush();
        // Soft reset with writebacks in flight, then bypass traffic whose B
        // must not be confused with the earlier writebacks' responses.
        t.range0_lo=0x1000; t.range0_hi=0x5000; t.range1_lo=0x8000; t.range1_hi=0xc000;
        for(unsigned i=0;i<120;i++) {
            for(unsigned k=0;k<24;k++) write(0x1000+((random()%48)*256)+(random()%16)*4,1+random()%8);
            uint32_t base=0x1000+(random()%4)*LINE_MODEL;
            write(base,2,15);
            for(unsigned w=1;w<=WAYS_MODEL;w++) write(base+w*LINE_MODEL*SETS_MODEL,1,15);
            soft_reset_then_bypass();
            read(0x1000,64); flush();
        }
        printf("PASS cycles=%llu memory_reads=%llu memory_writes=%llu\n",
               (unsigned long long)cycles,(unsigned long long)reads,(unsigned long long)writes);
    }
};
int main(int argc,char **argv) {
    Verilated::commandArgs(argc,argv);
    try { Test test; if(argc>1) test.rng=std::stoul(argv[1]); test.run(); }
    catch(const std::exception &e) { fprintf(stderr,"FAIL %s\n",e.what()); return 1; }
}
