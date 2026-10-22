// Mn103DecompileFile.java — 从文件读取地址列表，批量反编译对应函数
// 用法: -postScript Mn103DecompileFile.java <outFile> <addrListFile>
//   addrListFile 每行一个地址（0x 前缀十六进制或十进制），# 开头为注释
// @category EP5
import ghidra.app.script.GhidraScript;
import ghidra.app.decompiler.*;
import ghidra.program.model.listing.*;
import ghidra.program.model.address.Address;
import java.io.*;
import java.nio.file.*;
import java.util.*;

public class Mn103DecompileFile extends GhidraScript {
    @Override
    public void run() throws Exception {
        String[] args = getScriptArgs();
        String outFile = args.length > 0 ? args[0] : "decompile_file.txt";
        String listFile = args.length > 1 ? args[1] : null;
        if (listFile == null) { println("need addr list file"); return; }

        PrintWriter pw = new PrintWriter(new FileWriter(outFile));
        pw.println("# Mn103DecompileFile program=" + currentProgram.getName());

        DecompInterface di = new DecompInterface();
        di.setOptions(new DecompileOptions());
        di.toggleCCode(true);
        di.toggleSyntaxTree(true);
        di.setSimplificationStyle("decompile");
        if (!di.openProgram(currentProgram)) {
            pw.println("# decompiler open failed: " + di.getLastMessage());
            pw.flush(); pw.close();
            return;
        }

        FunctionManager fm = currentProgram.getFunctionManager();
        Set<Function> done = new HashSet<>();
        int n = 0;
        for (String line : Files.readAllLines(Paths.get(listFile))) {
            String s = line.trim();
            if (s.isEmpty() || s.startsWith("#")) continue;
            long v;
            try { v = s.startsWith("0x") || s.startsWith("0X")
                        ? Long.parseLong(s.substring(2), 16) : Long.parseLong(s); }
            catch (Exception e) { continue; }
            Address addr = toAddr(v);
            Function f = fm.getFunctionContaining(addr);
            if (f == null) { pw.println("NO FUNCTION at 0x" + Long.toHexString(v)); continue; }
            if (!done.add(f)) continue;
            n++;
            pw.println("==================================================================");
            pw.println("FUNCTION " + f.getName() + "  entry=" + f.getEntryPoint()
                    + "  body=" + f.getBody());
            DecompileResults res = di.decompileFunction(f, 90, monitor);
            if (res == null || !res.decompileCompleted()) {
                pw.println("  (decompile failed: "
                        + (res == null ? "null" : res.getErrorMessage()) + ")");
                continue;
            }
            DecompiledFunction df = res.getDecompiledFunction();
            if (df == null) { pw.println("  (no result)"); continue; }
            pw.println(df.getC());
            if ((n % 10) == 0) { pw.flush(); println("  ... " + n + " functions"); }
        }
        pw.flush(); pw.close(); di.dispose();
        println("Mn103DecompileFile DONE -> " + outFile + " funcs=" + n);
    }
}
