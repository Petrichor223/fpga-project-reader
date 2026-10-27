# Source only in an already open Vivado design. No compile/open/read_xdc side effects.
source [file join [file dirname [info script]] clock_query_common.tcl]
set ::fpga_clock_query::warnings {}
namespace eval ::fpga_clock_query {
    proc export_vivado {} {
        set design [current_design]
        if {$design eq ""} {error "Open an existing design before querying clocks"}
        set session [dict create project "" revision "" top $design device [query [list get_property PART $design]]]
        set project [query [list current_project -quiet]]
        if {$project ne ""} {
            dict set session project [query [list get_property NAME $project]]
        }
        set rows {}
        foreach clk [get_clocks -quiet *] {
            set row [dict create]
            foreach {field property} {
                name NAME period_ns PERIOD waveform_ns WAVEFORM generated IS_GENERATED
                virtual IS_VIRTUAL masters MASTER_CLOCK targets SOURCE_PINS source SOURCE
                multiply_by MULTIPLY_BY divide_by DIVIDE_BY inverted IS_INVERTED
                edges EDGES edge_shifts EDGE_SHIFT
            } {
                dict set row $field [query [list get_property $property $clk]]
            }
            # MASTER_CLOCK is a scalar clock name, which may itself contain spaces.
            set master [dict get $row masters]
            dict set row masters [expr {$master eq "" ? {} : [list $master]}]
            lappend rows [object $row {masters targets waveform_ns edges edge_shifts}]
        }
        write vivado [query [list version -short]] $session $rows
    }
}
::fpga_clock_query::export_vivado
