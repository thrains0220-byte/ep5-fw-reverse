// Mn103FindGlobalRefs.java — 找出引用某个 RAM 全局地址的所有函数
// 用法: -postScript Mn103FindGlobalRefs.java <outFile> <globalAddrHex> [globalAddrHex ...]
// @category EP5
import ghidra.app.script.GhidraScript;
import ghidra.program.model.listing.*;
import ghidra.program.model.address.Address;
import ghidra.program.model.mem.MemoryBlock;
import java.io.*;
import java.util.*;

public class Mn103FindGlobalRefs extends GhidraScript {
    @Override
    public void run() throws Exception {
        String[] args = getScriptArgs();
        String outFile = args.length > 0 ? args[0] : "globalrefs.txt";
        PrintWriter pw = new PrintWriter(new FileWriter(outFile));
        FunctionManager fm = currentProgram.getFunctionManager();
        Listing listing = currentProgram.getListing();

        for (int a = 1; a < args.length; a++) {
            long g = Long.decode(args[a]);
            pw.println("================ 全局 0x" + Long.toHexString(g) + " ================");
            InstructionIterator it = listing.getInstructions(true);
            int n = 0;
            while (it.hasNext()) {
                Instruction i = it.next();
                String s = i.toString();
                if (!s.toLowerCase().contains(Long.toHexString(g).toLowerCase())) continue;
                n++;
                Function f = fm.getFunctionContaining(i.getAddress());
                pw.println("  0x" + i.getAddress() + "  fn=" + ((f == null) ? "<none>" : f.getName())
                        + "   " + s);
            }
            pw.println("  -> 共 " + n + " 处\n");
        }
        pw.flush(); pw.close();
        println("Mn103FindGlobalRefs DONE -> " + outFile);
    }
}
