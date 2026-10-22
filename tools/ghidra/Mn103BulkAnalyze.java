//Bulk analysis for a flat (header-less) MN103 firmware image.
//
//A raw image has no entry points, so Ghidra's stock auto-analysis finds no
//functions.  This script
//   1. linearly disassembles the whole initialized code block,
//   2. creates a function at every CALL target (the real function entries in
//      MN103 code) and at the start of the block,
//   3. reports the resulting function inventory.
//
//Run as a post-script (no auto-analysis needed).

import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.TreeSet;

import ghidra.app.cmd.disassemble.DisassembleCommand;
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.address.AddressSet;
import ghidra.program.model.listing.Function;
import ghidra.program.model.listing.FunctionIterator;
import ghidra.program.model.listing.Instruction;
import ghidra.program.model.listing.InstructionIterator;
import ghidra.program.model.mem.MemoryBlock;
import ghidra.program.model.symbol.Reference;
import ghidra.program.model.symbol.ReferenceIterator;

public class Mn103BulkAnalyze extends GhidraScript {

    @Override
    public void run() throws Exception {
        MemoryBlock target = null;
        for (MemoryBlock b : currentProgram.getMemory().getBlocks()) {
            if (b.isInitialized() && b.getSize() > 0x100000) {
                target = b;
                break;
            }
        }
        if (target == null) {
            println("[Mn103BulkAnalyze] no initialized code block found");
            return;
        }
        println("[Mn103BulkAnalyze] block " + target.getName() + " " + target.getStart()
            + " - " + target.getEnd() + " r=" + target.isRead() + " w=" + target.isWrite()
            + " x=" + target.isExecute());

        long t0 = System.currentTimeMillis();

        // ---- 1. linear disassembly of the whole block --------------------------
        AddressSet set = new AddressSet(target.getStart(), target.getEnd());
        DisassembleCommand cmd = new DisassembleCommand(set, null, false);
        cmd.enableCodeAnalysis(false);
        boolean ok = cmd.applyTo(currentProgram, monitor);
        long t1 = System.currentTimeMillis();
        println("[Mn103BulkAnalyze] disassemble ok=" + ok + " in " + (t1 - t0) + " ms");

        long insnCount = 0;
        InstructionIterator it = currentProgram.getListing().getInstructions(target.getStart(), true);
        while (it.hasNext()) {
            Instruction insn = it.next();
            if (insn.getAddress().getOffset() > target.getEnd().getOffset()) {
                break;
            }
            insnCount++;
        }
        println("[Mn103BulkAnalyze] instructions decoded: " + insnCount);

        // ---- 2. collect CALL targets ------------------------------------------
        TreeSet<Long> callTargets = new TreeSet<Long>();
        TreeSet<Long> allRefTargets = new TreeSet<Long>();
        InstructionIterator it2 = currentProgram.getListing().getInstructions(target.getStart(), true);
        while (it2.hasNext()) {
            Instruction insn = it2.next();
            if (insn.getAddress().getOffset() > target.getEnd().getOffset()) {
                break;
            }
            for (Reference r : insn.getReferencesFrom()) {
                Address to = r.getToAddress();
                if (to == null || to.getAddressSpace() == null) {
                    continue;
                }
                if (!to.getAddressSpace().equals(currentProgram.getAddressFactory().getDefaultAddressSpace())) {
                    continue;
                }
                long off = to.getOffset();
                if (off < target.getStart().getOffset() || off > target.getEnd().getOffset()) {
                    continue;
                }
                allRefTargets.add(off);
                if (r.getReferenceType().isCall()) {
                    callTargets.add(off);
                }
            }
        }
        println("[Mn103BulkAnalyze] distinct in-block reference targets: " + allRefTargets.size());
        println("[Mn103BulkAnalyze] distinct in-block CALL targets       : " + callTargets.size());

        // ---- 3. create functions ----------------------------------------------
        int created = 0;
        int failed = 0;
        for (Long off : callTargets) {
            Address a = toAddr(off);
            if (currentProgram.getFunctionManager().getFunctionAt(a) != null) {
                continue;
            }
            if (createFunction(a, null) != null) {
                created++;
            }
            else {
                failed++;
            }
        }
        // and the very first word of the image
        Address blkStart = target.getStart();
        if (currentProgram.getFunctionManager().getFunctionAt(blkStart) == null
                && createFunction(blkStart, null) != null) {
            created++;
        }
        long t2 = System.currentTimeMillis();
        println("[Mn103BulkAnalyze] functions created: " + created + " (failed " + failed
            + ") in " + (t2 - t1) + " ms");

        int total = currentProgram.getFunctionManager().getFunctionCount();
        println("[Mn103BulkAnalyze] TOTAL FUNCTIONS IN PROGRAM: " + total);

        // ---- 4. inventory -------------------------------------------------------
        List<String> lines = new ArrayList<String>();
        FunctionIterator fi = currentProgram.getFunctionManager().getFunctions(true);
        while (fi.hasNext()) {
            Function f = fi.next();
            lines.add(String.format("%08x\t%s\t%d", f.getEntryPoint().getOffset(), f.getName(),
                f.getBody().getNumAddresses()));
        }
        Collections.sort(lines);
        String outPath = getScriptArgs().length > 0 ? getScriptArgs()[0] : ".";
        java.io.File out = new java.io.File(outPath, "mn103-all-functions.txt");
        java.io.PrintWriter pw = new java.io.PrintWriter(out, "UTF-8");
        for (String l : lines) {
            pw.println(l);
        }
        pw.close();
        println("[Mn103BulkAnalyze] wrote " + lines.size() + " functions to " + out.getAbsolutePath());

        // functions inside the art-filter window of interest
        int inWindow = 0;
        fi = currentProgram.getFunctionManager().getFunctions(toAddr(0x403B0000L), true);
        while (fi.hasNext()) {
            Function f = fi.next();
            if (f.getEntryPoint().getOffset() > 0x403FFFFFL) {
                break;
            }
            inWindow++;
            println(String.format("[Mn103BulkAnalyze] window fn %08x  %s", f.getEntryPoint().getOffset(),
                f.getName()));
        }
        println("[Mn103BulkAnalyze] functions in 0x403B0000..0x40400000: " + inWindow);
    }
}
