# Source in an already prepared Timing Analyzer session. Does not read/derive SDC.
source [file join [file dirname [info script]] clock_query_common.tcl]
set ::fpga_clock_query::warnings {}
namespace eval ::fpga_clock_query {
    proc export_quartus {} {
        set session [dict create project [query {get_current_project}] revision [query {get_current_revision}] \
            top [query {get_global_assignment -name TOP_LEVEL_ENTITY}] \
            device [query {get_global_assignment -name DEVICE}]]
        set rows {}
        # A missing timing netlist must fail here instead of producing a success artifact.
        foreach_in_collection clk [get_clocks *] {
            set row [dict create]
            foreach {field option} {
                name -name type -type period_ns -period waveform_ns -waveform
                multiply_by -multiply_by divide_by -divide_by inverted -is_inverted
                phase -phase edges -edges edge_shifts -edge_shifts
            } {
                dict set row $field [query [list get_clock_info $option $clk]]
            }
            set type [dict get $row type]
            dict set row generated [expr {$type in {generated virtual_generated}}]
            dict set row virtual [expr {$type in {virtual_base virtual_generated}}]
            set masters {}
            if {$type in {generated virtual_generated}} {
                set master [query [list get_clock_info -master_clock $clk]]
                if {$master ne ""} {lappend masters $master}
            }
            dict set row masters $masters
            set targets {}
            set collection [query [list get_clock_info -targets $clk]]
            if {$collection ne ""} {
                foreach_in_collection target $collection {
                    set name [query [list get_node_info -name $target]]
                    if {$name ne ""} {lappend targets $name}
                }
            }
            dict set row targets $targets
            lappend rows [object $row {masters targets waveform_ns edges edge_shifts}]
        }
        set version "unknown"
        if {[info exists ::quartus(version)]} {set version $::quartus(version)}
        write quartus $version $session $rows
    }
}
::fpga_clock_query::export_quartus
