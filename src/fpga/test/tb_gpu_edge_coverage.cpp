// SPDX-License-Identifier: Apache-2.0
// SPDX-FileCopyrightText: (c) 2026, ThinkElastic <Think@Elastic.com>
// Independent pixel-center coverage and shared-edge tests; no DDA reference.
#include "Vgpu_edge_walker.h"
#include "verilated.h"
#include <algorithm>
#include <array>
#include <cstdint>
#include <cstdio>
#include <vector>

struct Point { int x, y; };
using Tri = std::array<Point,3>;
static Vgpu_edge_walker dut;
static unsigned cycles;
static void tick() { dut.clk=0;dut.eval();dut.clk=1;dut.eval();++cycles; }
static int64_t edge(Point a,Point b,Point p) {
    return int64_t(b.x-a.x)*(p.y-a.y)-int64_t(b.y-a.y)*(p.x-a.x);
}
static int coverage(Tri t,int x,int y) {
    if(edge(t[0],t[1],t[2])<0)std::swap(t[1],t[2]);
    if(!edge(t[0],t[1],t[2]))return 0;
    Point p{x*16+8,y*16+8};
    bool boundary=false;
    for(int i=0;i<3;i++) {
        auto a=t[i],b=t[(i+1)%3];auto e=edge(a,b,p);
        if(e<0)return 0;
        if(!e)boundary=true;
    }
    return boundary?2:1;
}
static std::vector<unsigned> draw(Tri t) {
    std::vector<unsigned> fb(64*64);
    dut.v0_x=t[0].x;dut.v0_y=t[0].y;
    dut.v1_x=t[1].x;dut.v1_y=t[1].y;
    dut.v2_x=t[2].x;dut.v2_y=t[2].y;
    dut.start=1;tick();dut.start=0;
    for(unsigned n=0;n<10000;n++) {
        dut.rec_ready=(cycles%7)!=0;dut.eval();
        if(dut.rec_valid && dut.rec_ready) {
            int x=int16_t(dut.rec_u),y=int16_t(dut.rec_v),len=dut.rec_count;
            if(x<0 || y<0 || x+len>64 || y>=64) { std::fprintf(stderr,"Invalid span\n");std::exit(2); }
            for(int j=0;j<len;j++)fb[y*64+x+j]++;
        }
        tick();if(!dut.busy)return fb;
    }
    std::fprintf(stderr,"Walker timeout\n");std::exit(2);
}
int main(int argc,char **argv) {
    Verilated::commandArgs(argc,argv);
    dut.reset_n=0;dut.__SYM__abort=0;dut.start=0;dut.rec_ready=1;
    dut.subpix_y=1;dut.clip_x0=0;dut.clip_y0=0;dut.clip_x1=64;dut.clip_y1=64;
    tick();tick();dut.reset_n=1;tick();
    unsigned errors=0,checked=0,mesh_errors=0;
    // Fractional triangles in all vertex orders. Strict
    // interior/exterior checks avoid prescribing finite-precision diagonal ties.
    for(int phase=0;phase<16;phase++) {
        Tri t{{{16*3+phase,16*4+phase},{16*53+phase,16*11+phase},{16*9+phase,16*57+phase}}};
        for(int order=0;order<6;order++) {
            auto got=draw(t);
            for(int y=0;y<64;y++)for(int x=0;x<64;x++) {
                int ref=coverage(t,x,y);if(ref==2)continue;
                ++checked;if(got[y*64+x]!=unsigned(ref)){if(errors<6)std::printf("coverage mismatch phase=%d order=%d pixel=(%d,%d) got=%u expected=%d\n",phase,order,x,y,got[y*64+x],ref);++errors;}
            }
            if(order==2)std::swap(t[0],t[1]);else std::rotate(t.begin(),t.begin()+1,t.end());
        }
        Point a{16*2+phase,16*3+phase},b{16*61+phase,16*3+phase};
        Point c{16*61+phase,16*60+phase},d{16*2+phase,16*60+phase};
        // Both diagonals must tile the rectangle exactly once, including ties.
        for(int split=0;split<2;split++) {
            auto p=draw(split?Tri{{a,b,d}}:Tri{{a,b,c}});
            auto q=draw(split?Tri{{b,c,d}}:Tri{{a,c,d}});
            for(int y=0;y<64;y++)for(int x=0;x<64;x++) {
                int px=x*16+8,py=y*16+8;
                unsigned ref=px>=a.x&&px<b.x&&py>=a.y&&py<d.y;
                if(p[y*64+x]+q[y*64+x]!=ref)++mesh_errors;
            }
        }
        // Clipped fan: each shared edge appears as a long edge in one
        // triangle and a short edge in its neighbor. Exercise fractional
        // mid-vertex starts and scissor presteps without a DDA-derived oracle.
        a={-16*3+phase,-16*4+phase};b={16*61+phase,a.y};
        c={b.x,16*60+phase};d={a.x,c.y};Point center{16*17+phase,16*22+phase};
        std::vector<unsigned> fan(64*64);
        for(auto t: {Tri{{a,b,center}},Tri{{b,c,center}},Tri{{c,d,center}},Tri{{d,a,center}}}) {
            auto pixels=draw(t);for(unsigned i=0;i<fan.size();i++)fan[i]+=pixels[i];
        }
        for(int y=0;y<64;y++)for(int x=0;x<64;x++) {
            int px=x*16+8,py=y*16+8;
            unsigned ref=px>=a.x&&px<b.x&&py>=a.y&&py<d.y;
            if(fan[y*64+x]!=ref)++mesh_errors;
        }
    }
    std::printf("Pixel centers: %u checked, %u mismatches; shared-edge rectangle mismatches: %u\n",checked,errors,mesh_errors);
    return errors||mesh_errors?1:0;
}
