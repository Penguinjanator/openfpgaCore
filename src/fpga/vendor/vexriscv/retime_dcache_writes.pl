#!/usr/bin/env perl
# SPDX-License-Identifier: Apache-2.0
# Register the D$ data-bank write port and bypass the pending write into reads.
# A write sampled for edge E now reaches the RAM at edge E+1. A read captured at
# E+1 overlays the pending bytes on the RAM's OLD_DATA mixed-port result, so
# every read returns the same value as before. The late store hit, redo and
# byte-mask cone then ends at a register instead of every bank M10K write port.
use strict;
use warnings;

my $path = shift @ARGV or die "Usage: retime_dcache_writes.pl <netlist>\n";
@ARGV == 0 or die "Unexpected arguments\n";
open my $input, '<', $path or die "$path: $!\n";
my $source = do { local $/; <$input> };
close $input;
exit 0 if $source =~ /LsuL1Plugin_logic_banks_\d+_wq_we/;

sub replace_once {
    my ($before, $after) = @_;
    my $count = () = $source =~ /\Q$before\E/g;
    $count == 1 or die "Unexpected generated D\$ bank code: $before\n";
    $source =~ s/\Q$before\E/$after/;
}

sub width_of {
    my ($name) = @_;
    $source =~ /^  (?:wire|reg) +\[(\d+):0\] +\Q$name\E;$/m
        or die "Missing generated D\$ bank signal: $name\n";
    return $1 + 1;
}

my @banks = sort { $a <=> $b } ($source =~ /^  reg +\[\d+:0\] +LsuL1Plugin_logic_banks_(\d+)_mem_spinal_port1;$/mg);
@banks or die "No generated D\$ banks\n";

for my $bank (@banks) {
    my $p = "LsuL1Plugin_logic_banks_${bank}";
    my $aw = width_of("${p}_write_payload_address");
    my $dw = width_of("${p}_write_payload_data");
    my $mw = width_of("${p}_write_payload_mask");
    $dw == $mw * 8 or die "Unexpected D\$ bank symbol width in bank $bank\n";
    my $rw = width_of("${p}_read_cmd_payload");
    $rw == $aw or die "Mismatched D\$ bank address widths in bank $bank\n";

    my @reads;
    for my $s (0 .. $mw - 1) {
        my $lo = $s * 8;
        my $hi = $lo + 7;
        my $read = "_zz_${p}_memsymbol_read" . ($s ? "_$s" : "");
        replace_once(
            "    if(${p}_write_payload_mask[$s] && ${p}_write_valid) begin\n" .
            "      ${p}_mem_symbol$s\[${p}_write_payload_address] <= ${p}_write_payload_data[$hi : $lo];\n",
            "    if(${p}_wq_we[$s]) begin\n" .
            "      ${p}_mem_symbol$s\[${p}_wq_address] <= ${p}_wq_data[$hi : $lo];\n");
        index($source, "      $read <= ${p}_mem_symbol$s\[${p}_read_cmd_payload];\n") >= 0
            or die "Missing generated D\$ bank read: $read\n";
        unshift @reads, "(${p}_byp_hit[$s] ? ${p}_byp_data[$hi : $lo] : $read)";
    }
    my $old_port = "    ${p}_mem_spinal_port1 = {" .
        join(', ', map { "_zz_${p}_memsymbol_read" . ($_ ? "_$_" : "") } reverse 0 .. $mw - 1) .
        "};\n";
    replace_once($old_port, "    ${p}_mem_spinal_port1 = {" . join(', ', @reads) . "};\n");

    my $amsb = $aw - 1;
    my $dmsb = $dw - 1;
    my $mmsb = $mw - 1;
    my $declaration = "  reg [7:0] ${p}_mem_symbol0 [0:";
    my $state = "  reg [$mmsb:0] ${p}_wq_we;\n" .
        "  reg [$amsb:0] ${p}_wq_address;\n" .
        "  reg [$dmsb:0] ${p}_wq_data;\n" .
        "  reg [$mmsb:0] ${p}_byp_hit;\n" .
        "  reg [$dmsb:0] ${p}_byp_data;\n" .
        "  always @(posedge clk) begin\n" .
        "    ${p}_wq_we <= ${p}_write_payload_mask & {$mw\{${p}_write_valid}};\n" .
        "    ${p}_wq_address <= ${p}_write_payload_address;\n" .
        "    ${p}_wq_data <= ${p}_write_payload_data;\n" .
        "  end\n" .
        "  always @(posedge clk) begin\n" .
        "    if(${p}_read_cmd_valid) begin\n" .
        "      ${p}_byp_hit <= ${p}_wq_we & {$mw\{${p}_wq_address == ${p}_read_cmd_payload}};\n" .
        "      ${p}_byp_data <= ${p}_wq_data;\n" .
        "    end\n" .
        "  end\n";
    replace_once($declaration, $state . $declaration);
}

open my $output, '>', $path or die "$path: $!\n";
print {$output} $source;
close $output or die "$path: $!\n";
