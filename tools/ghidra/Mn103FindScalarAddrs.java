// Mn103FindScalarAddrs.java —— 枚举程序里所有「落在块 0 自身地址范围内的标量立即数」，
// 反推编译器是怎么形成字符串地址的（u32 立即数 / 高低半字两段式 / 基址+偏移）。
//
// 背景（第 24 轮）:
//     块 0 的字符串区（例如 'memdump' @0x40643861、'filetest:: *** START ***' @0x40644542）
//     用 u32 搜索、`fc dc`+u32、高/低半字对、u24、PC 相对 32 位偏移
//     **全部 0 命中**——但这些串必然被代码引用。
//     ⇒ 必须看指令级标量，才能知道真正的引用形式。
//
// 用法:
//   -postScript Mn103FindScalarAddrs.java <outFile> <lo> <hi> [minCount]
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.listing.Instruction;
import ghidra.program.model.listing.InstructionIterator;
import ghidra.program.model.scalar.Scalar;
import java.io.*;
import java.util.*;

public class Mn103FindScalarAddrs extends GhidraScript {
    @Override
    public void run() throws Exception {
        String[] args = getScriptArgs();
        String outFile = args.length > 0 ? args[0] : "scalars.txt";
        long lo = args.length > 1 ? Long.decode(args[1]) : 0x402C0000L;
        long hi = args.length > 2 ? Long.decode(args[2]) : 0x41200000L;
        int minCount = args.length > 3 ? Integer.parseInt(args[3]) : 1;

        PrintWriter pw = new PrintWriter(new FileWriter(outFile));
        pw.println("# Mn103FindScalarAddrs program=" + currentProgram.getName());
        pw.println("# range 0x" + Long.toHexString(lo) + "..0x" + Long.toHexString(hi));

        Map<Long, Integer> cnt = new TreeMap<>();
        Map<Long, String> sample = new HashMap<>();

        InstructionIterator it = currentProgram.getListing().getInstructions(true);
        int nInsn = 0, nScalar = 0;
        while (it.hasNext()) {
            Instruction ins = it.next();
            nInsn++;
            for (int i = 0; i < ins.getNumOperands(); i++) {
                for (Object o : ins.getOpObjects(i)) {
                    if (!(o instanceof Scalar)) continue;
                    long v = ((Scalar) o).getUnsignedValue();
                    nScalar++;
                    if (v < lo || v > hi) continue;
                    cnt.merge(v, 1, Integer::sum);
                    if (!sample.containsKey(v)) {
                        sample.put(v, "0x" + ins.getAddress().toString() + "  " + ins.toString());
                    }
                }
            }
        }
        pw.println("# instructions=" + nInsn + "  scalars=" + nScalar
                + "  distinct-in-range=" + cnt.size());
        pw.println();
        pw.println("# === 出现次数 >= " + minCount + " 的值 ===");
        for (Map.Entry<Long, Integer> e : cnt.entrySet()) {
            if (e.getValue() < minCount) continue;
            pw.println(String.format("0x%08X  x%-5d  %s",
                    e.getKey(), e.getValue(), sample.get(e.getKey())));
        }
        pw.flush(); pw.close();
        println("Mn103FindScalarAddrs DONE -> " + outFile);
    }
}
