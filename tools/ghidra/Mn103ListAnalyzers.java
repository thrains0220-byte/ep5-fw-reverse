//List every auto-analysis analyzer available for this program, with its
//current value, so the bulk "disassemble a flat image" analyzer can be
//enabled by its real name.

import java.util.Map;
import java.util.TreeMap;

import ghidra.app.script.GhidraScript;
import ghidra.program.model.listing.Program;

public class Mn103ListAnalyzers extends GhidraScript {

    @Override
    public void run() throws Exception {
        Program prog = currentProgram;
        println("=== ANALYZERS for " + prog.getLanguageID().getIdAsString() + " ===");
        Map<String, String> m = new TreeMap<String, String>(
            getCurrentAnalysisOptionsAndValues(prog));
        for (Map.Entry<String, String> e : m.entrySet()) {
            println(String.format("%-58s = %s", e.getKey(), e.getValue()));
        }
        println("total analyzers: " + m.size());
    }
}
