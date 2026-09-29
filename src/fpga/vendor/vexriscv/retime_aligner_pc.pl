#!/usr/bin/env perl
# SPDX-License-Identifier: Apache-2.0
# Preserve the aligner's enabled PC capture while registering its late enable.
# The raw/held selector has the same edge-to-edge value as the original PC.
use strict;
use warnings;

my $path = shift @ARGV or die "Usage: retime_aligner_pc.pl <netlist>\n";
@ARGV == 0 or die "Unexpected arguments\n";
open my $input, '<', $path or die "$path: $!\n";
my $source = do { local $/; <$input> };
close $input;
my $name = 'AlignerPlugin_logic_buffer_pc';
my $enable = 'when_AlignerPlugin_l256';
my $data = 'fetch_logic_ctrls_3_down_Fetch_WORD_PC';
my $declaration = "  wire [31:0] $name;\n" .
    "  reg [31:0] ${name}_raw;\n" .
    "  reg [31:0] ${name}_held;\n" .
    "  (* preserve, dont_retime *) reg ${name}_enabled;\n" .
    "  assign $name = ${name}_enabled ? ${name}_raw : ${name}_held;";
my $capture = "    ${name}_raw <= $data;\n" .
    "    ${name}_enabled <= $enable;\n" .
    "    if (${name}_enabled) ${name}_held <= ${name}_raw;\n";
exit 0 if index($source, $declaration) >= 0 && index($source, $capture) >= 0;

# Fail before writing if the generated aligner changes its capture contract.
$source =~ /^  reg +\[31:0\] +\Q$name\E;$/m
    or die "Missing aligner PC declaration\n";
my $old_declaration = $&;
my $assignment = "      $name <= $data;\n";
my $group = "    if($enable) begin\n";
my $writes = () = $source =~ /\b\Q$name\E\s*<=/g;
$writes == 1 && index($source, $assignment) >= 0
    or die "Unexpected aligner PC writer\n";
$source =~ /\Q$group\E(?:(?!^    end).)*?\Q$assignment\E/ms
    or die "Aligner PC no longer uses the expected enable\n";
my $old_group = $&;
my $new_group = $old_group;
$new_group =~ s/\Q$assignment\E//;
$source =~ s/\Q$old_declaration\E/$declaration/;
$source =~ s/\Q$old_group\E/$capture$new_group/;

open my $output, '>', $path or die "$path: $!\n";
print {$output} $source;
close $output or die "$path: $!\n";
