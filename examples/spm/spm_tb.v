module spm_tb; // The name of the testbench must match the one given when calling chip-vis.py

// Status register (value will be shown under each frame)
reg [8191:0] status = "Hello";

// Variables used in the testbench
reg [31:0] X = 0;
reg [31:0] Y = 0;
reg [63:0] P = 0;
wire p;

// Clock, reset, and power
reg clk = 0;
reg rst = 0;
reg pwr = 1'b0;
reg gnd = 1'b0;

// Instantiate the UUT (the name, "uut", is important when calling chip-vis.py)
spm uut (
	// Power and ground are required by the SKY130 cells
	.VPWR(pwr),
	.VGND(gnd),

	.clk(clk),
	.rst(rst),
	.y(Y[0]),
	.x(X),
	.p(p)
);

// Control clock
always #5 clk = pwr && ~clk;

// Logic used to interface with the UUT
always @(posedge clk) begin
	Y <= {1'b0, Y[31:1]};
	P <= {p, P[63:1]};
end

// Actual function to run the test - most of it is specific to this design,
// the important part is setting the `status` reg using $sformat
reg success;
reg [6:0] i;
task runTest (input [31:0] a, input [31:0] b);
	@(negedge clk);
	X = a;
	Y = b;
	i = 0;
	repeat (64) begin
		$sformat(status, "Calc %d * %d (%d/64)", a, b, i+1);
		i = i + 1;
		@(posedge clk);
	end
	repeat (2) @(posedge clk);
	success = (P / a) == b;
	$display("%d * %d = %d (%d)", a, b, P, success);
endtask

initial begin
	// THIS IS VERY IMPORTANT - ONLY DUMP THE "uut" and the "status" register,
	// not the whole testbench
	$dumpfile("spm.vcd");
	$dumpvars(0, uut);
	$dumpvars(0, status);

	// Power-up sequence
	clk = 0;
	pwr = 1;
	rst = 1;
	#10
	@(negedge clk);
	rst = 0;

	// Run all the tests
	runTest(1512427957, 1123428209);
	runTest(391912, 485732028);
	runTest(8447, 11231);

	$finish;
end

endmodule
