$date
	Sun Nov 22 17:42:30 2026
$end
$version
	Icarus Verilog
$end
$timescale
	1ps
$end
$scope module tb_top $end
$var wire 1 ! y $end
$var reg 1 " d0 $end
$var reg 1 # d1 $end
$var reg 1 $ d2 $end
$var reg 1 % d3 $end
$var reg 1 & s0 $end
$var reg 1 ' s1 $end
$var integer 32 ( fail_count [31:0] $end
$var integer 32 ) pass_count [31:0] $end
$var integer 32 * test_count [31:0] $end
$scope module dut $end
$var wire 1 " d0 $end
$var wire 1 # d1 $end
$var wire 1 $ d2 $end
$var wire 1 % d3 $end
$var wire 1 & s0 $end
$var wire 1 ' s1 $end
$var wire 1 ! y $end
$var wire 1 + mux2_out $end
$var wire 1 , mux1_out $end
$upscope $end
$scope task check_internal $end
$var reg 1 - expected_mux1_out $end
$var reg 1 . expected_mux2_out $end
$var reg 1 / expected_y $end
$var integer 32 0 errors [31:0] $end
$upscope $end
$upscope $end
$enddefinitions $end
#0
$dumpvars
bx 0
x/
x.
x-
0,
1+
b0 *
b0 )
b0 (
0'
0&
0%
1$
1#
0"
1!
$end
#10000
0!
1,
0+
1&
b1 *
b1 (
0/
1.
0-
b1 0
#20000
0,
0$
0&
1'
b10 *
b10 (
1/
0.
1-
b1 0
#30000
1!
1,
1+
1%
1$
1&
b11 *
b1 )
0/
0-
b0 0
#40000
0+
0!
0$
0#
1"
0&
0'
b100 *
b10 )
1/
1.
1-
#50000
1!
0,
1+
1$
1&
1'
b101 *
b11 (
b1 0
0.
#60000
b110 *
b11 )
1.
0-
b0 0
