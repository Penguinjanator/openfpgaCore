# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: (c) 2026, ThinkElastic <Think@Elastic.com>
# Check the enabled Pocket CRAM1 interface at every available timing corner.
# Run inside an os30 build: quartus_sta -t <this script> ap_core [report-dir]

set project [lindex $quartus(args) 0]
set destination [lindex $quartus(args) 1]
if {$destination eq ""} { set destination cram1_timing }
file mkdir $destination
project_open $project
create_timing_netlist -model slow
read_sdc
set inputs [get_ports {cram1_dq[*] cram1_wait}]
set outputs [get_ports {cram1_a[*] cram1_dq[*] cram1_adv_n cram1_ce0_n cram1_ce1_n cram1_oe_n cram1_we_n cram1_cre cram1_ub_n cram1_lb_n}]
set failures {}
foreach_in_collection corner [get_available_operating_conditions] {
    set_operating_conditions $corner
    update_timing_netlist
    set model [get_operating_conditions_info $corner -model]
    set temperature [get_operating_conditions_info $corner -temperature]
    foreach direction {input output} {
        if {$direction eq "input"} {
            set endpoint -from
            set pins $inputs
        } else {
            set endpoint -to
            set pins $outputs
        }
        foreach check {setup hold} {
            set label "${model}_${temperature}_${direction}_${check}"
            report_timing -$check $endpoint $pins -npaths 40 -detail summary \
                -file [file join $destination "$label.rpt"]
            set paths [get_timing_paths -$check $endpoint $pins -npaths 1]
            if {[get_collection_size $paths] == 0} {
                lappend failures "$label has no timed paths (use an enabled CRAM1 build)"
            } else {
                foreach_in_collection path $paths {
                    set slack [get_path_info $path -slack]
                    puts "CRAM1 $label slack=$slack ns"
                    if {$slack < 0} { lappend failures "$label slack=$slack ns" }
                }
            }
        }
    }
}
delete_timing_netlist
project_close
if {[llength $failures]} { error [join $failures "\n"] }
puts "CRAM1 setup/hold checks passed at every analyzed corner."
