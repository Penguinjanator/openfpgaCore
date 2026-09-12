#!/usr/bin/env perl
# SPDX-License-Identifier: Apache-2.0
# Preserve synchronous fetch reads while moving their late enables to registers.
# An enabled edge selects the new raw read. The first disabled edge captures
# the previous read in held; later disabled edges retain it. No read cycle is
# added, including when the underlying RAM is written during a stall.
use strict;
use warnings;

my $path = shift @ARGV or die "Usage: retime_fetch_reads.pl <netlist>\n";
@ARGV == 0 or die "Unexpected arguments\n";
open my $input, '<', $path or die "$path: $!\n";
my $source = do { local $/; <$input> };
close $input;
my $original = $source;

sub replace_once {
    my ($before, $after) = @_;
    my $count = () = $source =~ /\Q$before\E/g;
    $count == 1 or die "Unexpected generated read: $before\n";
    $source =~ s/\Q$before\E/$after/;
}

sub move_read_enable {
    my ($name, $enable, $data, $width) = @_;
    my $msb = $width - 1;
    my $declaration = "  wire [$msb:0] $name;\n" .
        "  reg [$msb:0] ${name}_raw;\n" .
        "  reg [$msb:0] ${name}_held;\n" .
        "  (* preserve, dont_retime *) reg ${name}_enabled;\n" .
        "  assign $name = ${name}_enabled ? ${name}_raw : ${name}_held;";
    my $replacement = "    ${name}_raw <= $data;\n" .
        "    ${name}_enabled <= $enable;\n" .
        "    if (${name}_enabled) ${name}_held <= ${name}_raw;";
    return if index($source, $declaration) >= 0 && index($source, $replacement) >= 0;
    $source =~ /^  reg +\[$msb:0\] +\Q$name\E;$/m
        or die "Missing generated fetch read register: $name\n";
    my $old_declaration = $&;
    my $body = "    if($enable) begin\n      $name <= $data;\n    end";
    replace_once($old_declaration, $declaration);
    replace_once($body, $replacement);
}

for my $bank (0, 1) {
    my $stem = "FetchL1Plugin_logic_banks_$bank";
    move_read_enable("${stem}_mem_spinal_port1", "${stem}_read_cmd_valid",
        "${stem}_mem[${stem}_read_cmd_payload]", 64);
}
move_read_enable("PrefetcherNextLinePlugin_logic_unbuffered_rData_pc",
    "PrefetcherNextLinePlugin_logic_unbuffered_ready",
    "PrefetcherNextLinePlugin_logic_unbuffered_payload_pc", 32);

# Write only after every expected read has been found and transformed.
if ($source ne $original) {
    open my $output, '>', $path or die "$path: $!\n";
    print {$output} $source;
    close $output or die "$path: $!\n";
}
