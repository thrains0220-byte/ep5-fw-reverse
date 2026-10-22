// Mn103DumpFuncs.java — dump 指定函数的完整反汇编 / 调用 / 数据引用
// 用法: -postScript Mn103DumpFuncs.java <outFile> <addr1> [addr2 ...]
// @category EP5
import ghidra.app.script.GhidraScript;
import ghidra.program.model.listing.*;
import ghidra.program.model.symbol.*;
import ghidra.program.model.address.Address;
import java.io.*;
import java.util.*;

public class Mn103DumpFuncs extends GhidraScript {
    @Override
    public void run() throws Exception {
        String[] args = getScriptArgs();
        String outFile = args.length > 0 ? args[0] : "funcs.txt";
        PrintWriter pw = new PrintWriter(new FileWriter(outFile));
        FunctionManager fm = currentProgram.getFunctionManager();
        Listing listing = currentProgram.getListing();

        for (int a = 1; a < args.length; a++) {
            Address addr = toAddr(Long.decode(args[a]));
            Function f = fm.getFunctionContaining(addr);
            pw.println("==================================================================");
            if (f == null) {
                pw.println("NO FUNCTION at " + addr);
                continue;
            }
            pw.println("FUNCTION " + f.getName() + "  entry=" + f.getEntryPoint()
                    + "  body=" + f.getBody());
            pw.println("  signature: " + f.getSignature());
            pw.println("--- disassembly ---");
            InstructionIterator it = listing.getInstructions(f.getBody(), true);
            while (it.hasNext()) {
                Instruction i = it.next();
                StringBuilder sb = new StringBuilder();
                sb.append(String.format("  0x%s  %-30s", i.getAddress(), i.toString()));
                for (Reference r : i.getReferencesFrom()) {
                    sb.append("   -> ").append(r.getReferenceType())
                      .append(" ").append(r.getToAddress());
                }
                pw.println(sb.toString());
            }
            pw.println("--- called functions ---");
            Set<String> callees = new TreeSet<>();
            it = listing.getInstructions(f.getBody(), true);
            while (it.hasNext()) {
                Instruction i = it.next();
                for (Reference r : i.getReferencesFrom()) {
                    Function cf = fm.getFunctionAt(r.getToAddress());
                    if (cf != null) callees.add(cf.getEntryPoint() + " " + cf.getName());
                    else callees.add("0x" + r.getToAddress() + " <data>");
                }
            }
            for (String c : callees) pw.println("  call " + c);
            pw.println();
        }
        pw.flush();
        pw.close();
        println("Mn103DumpFuncs DONE -> " + outFile);
    }
}
