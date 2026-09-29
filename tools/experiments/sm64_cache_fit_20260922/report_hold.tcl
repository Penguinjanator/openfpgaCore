package require ::quartus::project
package require ::quartus::sta
project_open [lindex $quartus(args) 0]
create_timing_netlist -model slow
read_sdc
foreach_in_collection corner [get_available_operating_conditions] {
    set model [get_operating_conditions_info $corner -model]
    set temperature [get_operating_conditions_info $corner -temperature]
    if {[string equal -nocase $model fast] && $temperature == 85} {
        set_operating_conditions $corner
        update_timing_netlist
        report_timing -hold -npaths 10 -detail full_path -file [lindex $quartus(args) 1]
    }
}
delete_timing_netlist
project_close
