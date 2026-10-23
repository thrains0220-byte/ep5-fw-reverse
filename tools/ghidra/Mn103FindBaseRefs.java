// Mn103FindBaseRefs.java —— 列出所有「加载某个基址立即数」的指令及其后继指令。
//
// 用途（第 25 轮）:
//     E-P5 块 0 里字符串不是用绝对地址引用的，而是
//         MOV  #<页基址>, A1
//         ADD  #<16 位偏移>, A1
//     本脚本把某个基址的所有引用点连同后继指令打出来，用于确认该模式，
//     并据此反查「哪个字符串被哪段代码用到」。
//
// 用法:
//   -postScript Mn103FindBaseRefs.java <outFile> <base1> [base2 ...]
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.listing.Function;
import ghidra.program.model.listing.Instruction;
import ghidra.program.model.listing.InstructionIterator;
import ghidra.program.model.scalar.Scalar;
import java.io.*;
import java.util.*;

public class Mn103FindBaseRefs extends GhidraScript {
    @Override
    public void run() throws Exception {
        String[] args = getScriptArgs();
        String outFile = args.length > 0 ? args[0] : "baserefs.txt";
        PrintWriter pw = new PrintWriter(new FileWriter(outFile));
        pw.println("# Mn103FindBaseRefs program=" + currentProgram.getName());

        for (int i = 1; i < args.length; i++) {
            long base = Long.decode(args[i]);
            pw.println("===== base 0x" + Long.toHexString(base) + " =====");
            InstructionIterator it = currentProgram.getListing().getInstructions(true);
            while (it.hasNext()) {
                Instruction ins = it.next();
                boolean hit = false;
                for (int o = 0; o < ins.getNumOperands() && !hit; o++) {
                    for (Object ob : ins.getOpObjects(o)) {
                        if (ob instanceof Scalar
                                && ((Scalar) ob).getUnsignedValue() == base) {
                            hit = true;
                        }
                    }
                }
                if (!hit) continue;
                Function f = getFunctionContaining(ins.getAddress());
                pw.println(String.format("  @0x%08X  in %s   |  %s",
                        ins.getAddress().getOffset(),
                        f == null ? "(nofunc)" : f.getName(), ins.toString()));
                Instruction nx = ins.getNext();
                for (int k = 0; k < 3 && nx != null; k++) {
                    pw.println(String.format("        +%d  0x%08X  %s",
                            k + 1, nx.getAddress().getOffset(), nx.toString()));
                    nx = nx.getNext();
                }
            }
            pw.println();
        }
        pw.flush(); pw.close();
        println("Mn103FindBaseRefs DONE -> " + outFile);
    }
}
