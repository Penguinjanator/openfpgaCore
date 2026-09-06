// Frozen arithmetic reference for the GPU area review.
// Intentionally retains the original wide operations for equivalence checks.

function [4:0] ref_clz32_fn;
    input [31:0] v;
    begin
        casez (v)
            32'b1???????????????????????????????: ref_clz32_fn = 5'd0;
            32'b01??????????????????????????????: ref_clz32_fn = 5'd1;
            32'b001?????????????????????????????: ref_clz32_fn = 5'd2;
            32'b0001????????????????????????????: ref_clz32_fn = 5'd3;
            32'b00001???????????????????????????: ref_clz32_fn = 5'd4;
            32'b000001??????????????????????????: ref_clz32_fn = 5'd5;
            32'b0000001?????????????????????????: ref_clz32_fn = 5'd6;
            32'b00000001????????????????????????: ref_clz32_fn = 5'd7;
            32'b000000001???????????????????????: ref_clz32_fn = 5'd8;
            32'b0000000001??????????????????????: ref_clz32_fn = 5'd9;
            32'b00000000001?????????????????????: ref_clz32_fn = 5'd10;
            32'b000000000001????????????????????: ref_clz32_fn = 5'd11;
            32'b0000000000001???????????????????: ref_clz32_fn = 5'd12;
            32'b00000000000001??????????????????: ref_clz32_fn = 5'd13;
            32'b000000000000001?????????????????: ref_clz32_fn = 5'd14;
            32'b0000000000000001????????????????: ref_clz32_fn = 5'd15;
            32'b00000000000000001???????????????: ref_clz32_fn = 5'd16;
            32'b000000000000000001??????????????: ref_clz32_fn = 5'd17;
            32'b0000000000000000001?????????????: ref_clz32_fn = 5'd18;
            32'b00000000000000000001????????????: ref_clz32_fn = 5'd19;
            32'b000000000000000000001???????????: ref_clz32_fn = 5'd20;
            32'b0000000000000000000001??????????: ref_clz32_fn = 5'd21;
            32'b00000000000000000000001?????????: ref_clz32_fn = 5'd22;
            32'b000000000000000000000001????????: ref_clz32_fn = 5'd23;
            32'b0000000000000000000000001???????: ref_clz32_fn = 5'd24;
            32'b00000000000000000000000001??????: ref_clz32_fn = 5'd25;
            32'b000000000000000000000000001?????: ref_clz32_fn = 5'd26;
            32'b0000000000000000000000000001????: ref_clz32_fn = 5'd27;
            32'b00000000000000000000000000001???: ref_clz32_fn = 5'd28;
            32'b000000000000000000000000000001??: ref_clz32_fn = 5'd29;
            32'b0000000000000000000000000000001?: ref_clz32_fn = 5'd30;
            default: ref_clz32_fn = 5'd31;
        endcase
    end
endfunction

function [15:0] ref_z_compress;
    input [31:0] v;
    integer i;
    reg [4:0]  e;
    reg        found;
    reg [10:0] mant;
    begin
        if (v == 32'd0) begin
            ref_z_compress = 16'd0;
        end else begin
            e = 5'd0; found = 1'b0;
            for (i = 31; i >= 0; i = i - 1) begin
                if (!found && v[i]) begin
                    e = i[4:0];
                    found = 1'b1;
                end
            end
            if (e >= 5'd11)
                mant = v >> (e - 5'd11);   // 11 bits below the leading 1
            else
                mant = v << (5'd11 - e);   // small value: left-align low bits
            ref_z_compress = {e, mant};
        end
    end
endfunction

function [37:0] ref_zc_stage1;
    input [31:0] v;
    integer i;
    reg [4:0] e; reg found;
    begin
        e = 5'd0; found = 1'b0;
        for (i = 31; i >= 0; i = i - 1)
            if (!found && v[i]) begin e = i[4:0]; found = 1'b1; end
        ref_zc_stage1 = {(v == 32'd0), e, v};   // [37]=is_zero, [36:32]=e, [31:0]=v
    end
endfunction

function [15:0] ref_zc_stage2;
    input [37:0] s1;
    reg is_zero; reg [4:0] e; reg [31:0] v; reg [10:0] mant;
    begin
        is_zero = s1[37]; e = s1[36:32]; v = s1[31:0];
        if (is_zero) ref_zc_stage2 = 16'd0;
        else begin
            if (e >= 5'd11) mant = v >> (e - 5'd11);
            else            mant = v << (5'd11 - e);
            ref_zc_stage2 = {e, mant};
        end
    end
endfunction

function signed [31:0] ref_q29_restore_z_saturating;
    input signed [31:0] value;
    input [4:0] shift;
    reg signed [63:0] wide;
    begin
        wide = $signed({{32{value[31]}}, value}) <<< shift;
        if (wide[63:31] != {33{wide[31]}})
            ref_q29_restore_z_saturating = wide[63] ? 32'sh80000000 : 32'sh7fffffff;
        else
            ref_q29_restore_z_saturating = wide[31:0];
    end
endfunction


function [15:0] ref_mirror_idx;
    input [15:0] raw;        // clamped coord integer part
    input [15:0] mask;       // sp_tex_w_mask / sp_tex_h_mask (W-1 for POT)
    input [15:0] octave;     // precomputed mask+1 mod 2^16 (span-constant;
                             // sp_tex_w_octave / sp_tex_h_octave)
    input        mirror_en;
    reg   [15:0] wrapped;
    begin
        wrapped = raw & mask;
        if (mirror_en && ((raw & octave) != 16'd0))
            ref_mirror_idx = mask - wrapped;   // reversed half of the 2W period
        else
            ref_mirror_idx = wrapped;
    end
endfunction

function signed [31:0] ref_sat_add32;
    input signed [31:0] a;
    input signed [31:0] b;
    reg signed [32:0] sum;
    begin
        sum = {a[31], a} + {b[31], b};
        if (sum[32] != sum[31])
            ref_sat_add32 = sum[32] ? 32'sh80000000 : 32'sh7fffffff;
        else
            ref_sat_add32 = sum[31:0];
    end
endfunction
