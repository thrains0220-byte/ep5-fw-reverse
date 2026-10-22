// Mn103DisasmRange.java — 反汇编指定地址区间（不要求已有函数）
// 用法: -postScript Mn103DisasmRange.java <outFile> <loAddr> <hiAddr>
// @category EP5
import ghidra.app.script.GhidraScript;
import ghidra.program.model.listing.*;
import ghidra.program.model.address.Address;
import java.io.*;

public class Mn103DisasmRange extends GhidraScript {
    @Override
    public void run() throws Exception {
        String[] args = getScriptArgs();
        String outFile = args.length > 0 ? args[0] : "disasm.txt";
        Address lo = toAddr(Long.decode(args[1]));
        Address hi = toAddr(Long.decode(args[2]));
        PrintWriter pw = new PrintWriter(new FileWriter(outFile));
        Listing listing = currentProgram.getListing();
        FunctionManager fm = currentProgram.getFunctionManager();
        pw.println("# Mn103DisasmRange  0x" + lo + " .. 0x" + hi);
        InstructionIterator it = listing.getInstructions(lo, true);
        int n = 0;
        while (it.hasNext()) {
            Instruction i = it.next();
            if (i.getAddress().compareTo(hi) > 0) break;
            n++;
            Function f = fm.getFunctionContaining(i.getAddress());
            pw.printf("  0x%s  %-26s %s%n", i.getAddress(),
                    (f == null) ? "<no-fn>" : f.getName(), i.toString());
        }
        pw.flush(); pw.close();
        println("Mn103DisasmRange DONE: " + n + " 条指令 -> " + outFile);
    }
}
