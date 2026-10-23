// Mn103FindXrefs.java —— 用 Ghidra 原生引用分析查「数据地址 → 代码引用」。
//
// 用途（第 24 轮）:
//     相机固件里存在内置的文件系统调试命令
//     「memdump NAME ADR LEN - dump memory into file」，
//     但字符串地址在块 0 里搜不到任何 u32 指针（既不在本块也不在其余三块），
//     说明引用方式不是 `MOV #imm32, A0`，需要 Ghidra 的数据流引用分析来定位。
//
// 用法:
//   -postScript Mn103FindXrefs.java <outFile> <addr1> [addr2 ...]
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.listing.Function;
import ghidra.program.model.symbol.Reference;
import ghidra.program.model.symbol.ReferenceIterator;
import java.io.*;

public class Mn103FindXrefs extends GhidraScript {
    @Override
    public void run() throws Exception {
        String[] args = getScriptArgs();
        String outFile = args.length > 0 ? args[0] : "xrefs.txt";
        PrintWriter pw = new PrintWriter(new FileWriter(outFile));
        pw.println("# Mn103FindXrefs program=" + currentProgram.getName());
        for (int i = 1; i < args.length; i++) {
            Address a = toAddr(Long.decode(args[i]));
            pw.println("===== " + a + " =====");
            Function f = getFunctionContaining(a);
            pw.println("  containing function: " +
                (f == null ? "(none)" : f.getName() + " @" + f.getEntryPoint()));
            ReferenceIterator it = currentProgram.getReferenceManager()
                    .getReferencesTo(a);
            int n = 0;
            while (it.hasNext()) {
                Reference r = it.next();
                Function rf = getFunctionContaining(r.getFromAddress());
                pw.println("  ref from 0x" + r.getFromAddress().toString()
                        + "  type=" + r.getReferenceType()
                        + "  in=" + (rf == null ? "(none)" : rf.getName()
                        + "@" + rf.getEntryPoint()));
                n++;
            }
            pw.println("  -> " + n + " refs");
            pw.println();
        }
        pw.flush(); pw.close();
        println("Mn103FindXrefs DONE -> " + outFile);
    }
}
