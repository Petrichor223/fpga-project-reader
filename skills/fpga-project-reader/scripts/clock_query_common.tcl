# Shared JSON writer for read-only clock exporters. Tcl 8.5+, no extra packages.
namespace eval ::fpga_clock_query {
    variable warnings {}
    proc quote {value} {
        set out {"}
        foreach char [split $value ""] {
            scan $char %c code
            if {$code == 34} {append out {\"}} elseif {$code == 92} {
                append out {\\}
            } elseif {$code < 32} {
                append out [format {\u%04x} $code]
            } else {append out $char}
        }
        append out {"}
        return $out
    }
    proc array {values} {
        set out {}
        foreach v $values {lappend out [quote $v]}
        return \[[join $out ,]\]
    }
    proc object {values {arrays {}}} {
        set out {}
        dict for {key value} $values {
            if {$key in $arrays} {set encoded [array $value]} else {set encoded [quote $value]}
            lappend out "[quote $key]:$encoded"
        }
        return \{[join $out ,]\}
    }
    proc query {command} {
        variable warnings
        if {[catch {uplevel #0 $command} result]} {
            lappend warnings "$command: $result"
            return ""
        }
        return $result
    }
    proc write {vendor version session rows} {
        variable warnings
        if {![info exists ::fpga_reader_clock_export] ||
            [file pathtype $::fpga_reader_clock_export] ne "absolute"} {
            error "Set fpga_reader_clock_export to an absolute output JSON path first"
        }
        set path $::fpga_reader_clock_export
        # Exclusive creation prevents accidental overwriting of hand-maintained data.
        file mkdir [file dirname $path]
        set f [open $path {WRONLY CREAT EXCL}]
        fconfigure $f -encoding utf-8 -translation lf
        set body "\{\"format\":\"fpga-clock-query-v1\",\"vendor\":[quote $vendor],\"tool_version\":[quote $version],\"exported_utc\":[quote [clock format [clock seconds] -gmt 1 -format {%Y-%m-%dT%H:%M:%SZ}]],\"session\":[object $session],\"clocks\":\[[join $rows ,]\],\"warnings\":[array $warnings]\}"
        puts $f $body
        close $f
        puts "FPGA reader clock query exported: $path"
    }
}
