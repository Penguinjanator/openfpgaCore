# Check setup, hold, recovery, removal and pulse width at every corner.
# Run in a completed Quartus project directory:
#   quartus_sta -t /path/to/report_core_timing.tcl <project> <report-directory>
# Negative slack or missing setup/hold/pulse-width checks exit unsuccessfully.
# Unconstrained paths still require interface-specific review.

package require ::quartus::project
package require ::quartus::sta

if {[llength $quartus(args)] != 2} {
    error "Usage: report_core_timing.tcl <project> <report-directory>"
}
set project [lindex $quartus(args) 0]
set destination [lindex $quartus(args) 1]
file mkdir $destination
project_open $project
create_timing_netlist -model slow
read_sdc

set summary [open [file join $destination summary.tsv] w]
set clock_summary [open [file join $destination clocks.tsv] w]
puts $summary "model\ttemperature\tcheck\tslack"
puts $clock_summary "model\ttemperature\tcheck\tclock\tslack"
set failed 0
set corner_count 0
foreach_in_collection corner [get_available_operating_conditions] {
    incr corner_count
    set_operating_conditions $corner
    update_timing_netlist
    set model [get_operating_conditions_info $corner -model]
    set temperature [get_operating_conditions_info $corner -temperature]
    foreach check {setup hold recovery removal} {
        set label "${model}_${temperature}_${check}"
        report_timing -$check -npaths 20 -detail full_path \
            -file [file join $destination "$label.rpt"]
        set paths [get_timing_paths -$check -npaths 1]
        if {[get_collection_size $paths] == 0} {
            puts $summary "$model\t$temperature\t$check\tno_paths"
            # A fully synchronous reset design can have no asynchronous checks.
            if {$check eq "setup" || $check eq "hold"} { set failed 1 }
        }
        foreach_in_collection path $paths {
            set slack [get_path_info $path -slack]
            puts $summary "$model\t$temperature\t$check\t$slack"
            puts "RESULT $label $slack"
            if {$slack < 0} { set failed 1 }
        }
        foreach_in_collection clk [get_clocks] {
            set name [get_clock_info -name $clk]
            set paths [get_timing_paths -$check -to_clock $clk -npaths 1]
            set slack no_paths
            foreach_in_collection path $paths {
                set slack [get_path_info $path -slack]
            }
            puts $clock_summary "$model\t$temperature\t$check\t$name\t$slack"
        }
    }
    set pulse_report [file join $destination "${model}_${temperature}_pulse_width.rpt"]
    report_min_pulse_width -nworst 20 -detail summary -file $pulse_report
    set stream [open $pulse_report r]
    set pulse_slack no_paths
    while {[gets $stream line] >= 0} {
        if {![string match ";*" $line]} { continue }
        set value [string trim [lindex [split $line ";"] 1]]
        if {![string is double -strict $value]} { continue }
        if {$pulse_slack eq "no_paths" || $value < $pulse_slack} {
            set pulse_slack $value
        }
    }
    close $stream
    puts $summary "$model\t$temperature\tpulse_width\t$pulse_slack"
    puts "RESULT ${model}_${temperature}_pulse_width $pulse_slack"
    if {$pulse_slack eq "no_paths" || $pulse_slack < 0} { set failed 1 }
}
if {$corner_count == 0} { set failed 1 }
close $summary
close $clock_summary
delete_timing_netlist
project_close
if {$failed} { error "Whole-design timing failed; see $destination" }
