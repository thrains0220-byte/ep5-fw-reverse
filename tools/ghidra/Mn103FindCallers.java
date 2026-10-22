// Mn103FindCallers.java — 找出调用某函数的全部位置，并打印实参（紧邻的 MOV imm,D0）
// 用法: -postScript Mn103FindCallers.java <outFile> <targetAddrHex> [targetAddrHex ...]
// @category EP5
import ghidra.app.script.GhidraScript;
import ghidra.program.model.listing.*;
import ghidra.program.model.address.Address;
import java.io.*;
import java.util.*;

public class Mn103FindCallers extends GhidraScript {
    @Override
    public void run() throws Exception {
        String[] args = getScriptArgs();
        String outFile = args.length > 0 ? args[0] : "callers.txt";
        PrintWriter pw = new PrintWriter(new FileWriter(outFile));
        FunctionManager fm = currentProgram.getFunctionManager();
        Listing listing = currentProgram.getListing();

        for (int a = 1; a < args.length; a++) {
            Address tgt = toAddr(Long.decode(args[a]));
            pw.println("=========== 调用者 of 0x" + tgt + " ===========");
            InstructionIterator it = listing.getInstructions(true);
            int n = 0;
            while (it.hasNext()) {
                Instruction i = it.next();
                String s = i.toString().toUpperCase();
                if (!s.startsWith("CALL")) continue;
                if (!s.contains(tgt.toString().toUpperCase())) continue;
                n++;
                Function f = fm.getFunctionContaining(i.getAddress());
                pw.println("  0x" + i.getAddress() + "  fn="
                        + ((f == null) ? "<none>" : f.getName()) + "   " + i.toString());
                // 向前打印 6 条指令（实参通常在这里）
                Instruction prev = i.getPrevious();
                int k = 0;
                while (prev != null && k < 6) {
                    pw.println("        ^ " + prev.toString());
                    prev = prev.getPrevious();
                    k++;
                }
            }
            pw.println("  -> " + n + " 个调用点\n");
        }
        pw.flush(); pw.close();
        println("Mn103FindCallers DONE -> " + outFile);
    }
}
