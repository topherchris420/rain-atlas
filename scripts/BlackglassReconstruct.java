// BLACK GLASS: deterministic, read-only Ghidra routine-reconstruction exporter (Java).
//@category BLACK_GLASS
//
// Ghidra 12 runs .java GhidraScripts with its bundled JDK (no Python/PyGhidra needed).
// For each seed address it resolves the containing function (or, for a data seed, the
// functions that reference it), emits derived facts (callees, referenced strings,
// notable constants, basic-block count) and writes the decompiled pseudocode to a LOCAL
// file whose SHA-256 is recorded. The pseudocode is evidence held locally; only its
// digest and the non-copyrightable facts enter the committed model. The script never
// changes program bytes, names or types, and refuses to run on a hash mismatch.
//
// analyzeHeadless usage:
//   -postScript BlackglassReconstruct.java <relative-binary-path> <absolute-ELF-path> \
//       <output-dir> <seed-hex> [<seed-hex> ...]

import java.io.File;
import java.io.FileInputStream;
import java.io.FileOutputStream;
import java.io.OutputStreamWriter;
import java.io.Writer;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.ArrayList;
import java.util.Collections;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.TreeSet;

import ghidra.app.decompiler.DecompInterface;
import ghidra.app.decompiler.DecompileResults;
import ghidra.app.script.GhidraScript;
import ghidra.framework.Application;
import ghidra.program.model.address.Address;
import ghidra.program.model.block.BasicBlockModel;
import ghidra.program.model.block.CodeBlockIterator;
import ghidra.program.model.listing.Data;
import ghidra.program.model.listing.Function;
import ghidra.program.model.listing.FunctionManager;
import ghidra.program.model.listing.Instruction;
import ghidra.program.model.listing.Listing;
import ghidra.program.model.scalar.Scalar;
import ghidra.program.model.symbol.Reference;

public class BlackglassReconstruct extends GhidraScript {

    @Override
    public void run() throws Exception {
        String[] args = getScriptArgs();
        if (args.length < 4) {
            throw new IllegalArgumentException(
                "expected: <relative-binary-path> <absolute-ELF-path> <output-dir> <seed-hex>...");
        }
        String relativePath = args[0];
        String binaryPath = args[1];
        String outputDir = args[2];

        String fileSha = sha256File(binaryPath);
        String importSha = currentProgram.getExecutableSHA256();
        if (importSha == null || !importSha.toLowerCase().equals(fileSha)) {
            throw new IllegalStateException("Ghidra program import SHA256 does not match the source ELF");
        }
        File outDir = new File(outputDir);
        if (!outDir.isDirectory() && !outDir.mkdirs()) {
            throw new IllegalStateException("cannot create output directory: " + outputDir);
        }

        Listing listing = currentProgram.getListing();
        FunctionManager fm = currentProgram.getFunctionManager();
        BasicBlockModel bbm = new BasicBlockModel(currentProgram);
        DecompInterface decomp = new DecompInterface();
        decomp.openProgram(currentProgram);

        List<String> routineJson = new ArrayList<>();
        LinkedHashSet<Long> emitted = new LinkedHashSet<>();

        for (int s = 3; s < args.length; s++) {
            String seed = args[s];
            long seedVal = Long.parseLong(seed.replaceFirst("0x", ""), 16);
            Address addr = toAddr(seedVal);
            List<Function> funcs = new ArrayList<>();
            String how;
            Function direct = getFunctionContaining(addr);
            if (direct != null) {
                funcs.add(direct);
                how = "code";
            } else {
                how = "data-xref";
                LinkedHashSet<Long> seen = new LinkedHashSet<>();
                for (Reference ref : getReferencesTo(addr)) {
                    Function caller = getFunctionContaining(ref.getFromAddress());
                    if (caller != null && seen.add(caller.getEntryPoint().getOffset())) {
                        funcs.add(caller);
                        if (funcs.size() >= 8) {
                            break;
                        }
                    }
                }
            }
            for (Function function : funcs) {
                long key = function.getEntryPoint().getOffset();
                if (!emitted.add(key)) {
                    continue;
                }
                monitor.checkCancelled();
                routineJson.add(routineRecord(function, listing, fm, bbm, decomp, outputDir, seed, how));
            }
        }

        Collections.sort(routineJson);  // entry address is the first field, so lexical order ~ address order
        StringBuilder doc = new StringBuilder();
        doc.append("{\n");
        doc.append("  \"schema\": \"blackglass.native-reconstruction/v1\",\n");
        doc.append("  \"tool\": \"ghidra-headless\",\n");
        doc.append("  \"tool_version\": ").append(jsonStr(Application.getApplicationVersion())).append(",\n");
        doc.append("  \"binary\": ").append(jsonStr(relativePath)).append(",\n");
        doc.append("  \"sha256\": ").append(jsonStr("sha256:" + fileSha)).append(",\n");
        doc.append("  \"architecture\": ")
            .append(jsonStr(currentProgram.getLanguage().getProcessor().toString())).append(",\n");
        doc.append("  \"routines\": [\n");
        for (int i = 0; i < routineJson.size(); i++) {
            doc.append(routineJson.get(i));
            doc.append(i + 1 < routineJson.size() ? ",\n" : "\n");
        }
        doc.append("  ]\n}\n");

        File outJson = new File(outDir, "reconstruction.json");
        try (Writer w = new OutputStreamWriter(new FileOutputStream(outJson), StandardCharsets.UTF_8)) {
            w.write(doc.toString());
        }
        println("BLACK GLASS reconstruct: " + routineJson.size() + " routines -> " + outJson.getAbsolutePath());
    }

    private String routineRecord(Function function, Listing listing, FunctionManager fm, BasicBlockModel bbm,
                                 DecompInterface decomp, String outputDir, String seed, String how)
            throws Exception {
        TreeSet<String> callees = new TreeSet<>();
        TreeSet<String> strings = new TreeSet<>();
        TreeSet<Long> constants = new TreeSet<>();
        for (Instruction instruction : listing.getInstructions(function.getBody(), true)) {
            for (Reference reference : instruction.getReferencesFrom()) {
                Address target = reference.getToAddress();
                if (reference.getReferenceType().isCall()) {
                    Function callee = fm.getFunctionAt(target);
                    if (callee == null) {
                        callee = fm.getFunctionContaining(target);
                    }
                    callees.add(callee != null ? callee.getName() : ("0x" + Long.toHexString(target.getOffset())));
                }
                Data data = listing.getDataAt(target);
                if (data != null && data.hasStringValue() && data.getValue() != null) {
                    String str = data.getValue().toString();
                    if (!str.isEmpty()) {
                        strings.add(str.length() > 120 ? str.substring(0, 120) : str);
                    }
                } else if (!reference.getReferenceType().isCall()) {
                    // Referenced data that Ghidra did not type as a string (e.g. a char
                    // lookup table indexed by code): record a printable run as evidence.
                    String printable = printableAt(target);
                    if (printable != null) {
                        strings.add(printable);
                    }
                }
            }
            for (int i = 0; i < instruction.getNumOperands(); i++) {
                Scalar scalar = instruction.getScalar(i);
                if (scalar != null) {
                    long v = scalar.getUnsignedValue();
                    // Unsigned comparison: a 64-bit immediate like 0xefcdab8967452301 is
                    // negative as a signed long and must not be dropped.
                    if (Long.compareUnsigned(v, 0xFFFFL) > 0 && v != 0xFFFFFFFFL && v != -1L) {
                        constants.add(v);
                    }
                }
            }
        }
        int blocks = 0;
        CodeBlockIterator it = bbm.getCodeBlocksContaining(function.getBody(), monitor);
        while (it.hasNext()) {
            it.next();
            blocks++;
        }
        String decompSha = null;
        String decompFile = null;
        DecompileResults results = decomp.decompileFunction(function, 90, monitor);
        if (results != null && results.decompileCompleted() && results.getDecompiledFunction() != null) {
            String text = results.getDecompiledFunction().getC();
            String fname = function.getName() + "_0x" + Long.toHexString(function.getEntryPoint().getOffset()) + ".c";
            File cf = new File(outputDir, fname);
            try (Writer w = new OutputStreamWriter(new FileOutputStream(cf), StandardCharsets.UTF_8)) {
                w.write(text);
            }
            decompSha = "sha256:" + sha256Bytes(text.getBytes(StandardCharsets.UTF_8));
            decompFile = fname;
        }

        StringBuilder r = new StringBuilder();
        r.append("    {\n");
        r.append("      \"entry\": \"0x").append(Long.toHexString(function.getEntryPoint().getOffset())).append("\",\n");
        r.append("      \"name\": ").append(jsonStr(function.getName())).append(",\n");
        r.append("      \"size\": ").append(function.getBody().getNumAddresses()).append(",\n");
        r.append("      \"basic_blocks\": ").append(blocks).append(",\n");
        r.append("      \"seed\": ").append(jsonStr(seed)).append(",\n");
        r.append("      \"seed_resolution\": ").append(jsonStr(how)).append(",\n");
        r.append("      \"callees\": ").append(jsonStrArray(new ArrayList<>(callees))).append(",\n");
        r.append("      \"string_refs\": ").append(jsonStrArray(new ArrayList<>(strings))).append(",\n");
        r.append("      \"constants\": ").append(jsonHexArray(constants)).append(",\n");
        r.append("      \"decompilation_sha256\": ").append(decompSha == null ? "null" : jsonStr(decompSha)).append(",\n");
        r.append("      \"decompilation_file\": ").append(decompFile == null ? "null" : jsonStr(decompFile)).append("\n");
        r.append("    }");
        return r.toString();
    }

    // Read a run of printable ASCII at an address, for referenced data Ghidra did
    // not type as a string (e.g. a base64 lookup table indexed by code). Read-only.
    private String printableAt(Address addr) {
        try {
            ghidra.program.model.mem.Memory mem = currentProgram.getMemory();
            if (!mem.contains(addr)) {
                return null;
            }
            StringBuilder b = new StringBuilder();
            for (int i = 0; i < 128; i++) {
                int c;
                try {
                    c = mem.getByte(addr.add(i)) & 0xff;
                } catch (Exception e) {
                    break;
                }
                if (c >= 0x20 && c <= 0x7e) {
                    b.append((char) c);
                } else {
                    break;
                }
            }
            if (b.length() < 8) {
                return null;
            }
            return b.length() > 120 ? b.substring(0, 120) : b.toString();
        } catch (Exception e) {
            return null;
        }
    }

    private static String jsonStr(String s) {
        StringBuilder b = new StringBuilder("\"");
        for (int i = 0; i < s.length(); i++) {
            char c = s.charAt(i);
            switch (c) {
                case '"': b.append("\\\""); break;
                case '\\': b.append("\\\\"); break;
                case '\n': b.append("\\n"); break;
                case '\r': b.append("\\r"); break;
                case '\t': b.append("\\t"); break;
                default:
                    if (c < 0x20 || c > 0x7e) {
                        b.append(String.format("\\u%04x", (int) c));
                    } else {
                        b.append(c);
                    }
            }
        }
        return b.append("\"").toString();
    }

    private static String jsonStrArray(List<String> items) {
        StringBuilder b = new StringBuilder("[");
        for (int i = 0; i < items.size(); i++) {
            b.append(jsonStr(items.get(i)));
            if (i + 1 < items.size()) {
                b.append(", ");
            }
        }
        return b.append("]").toString();
    }

    private static String jsonHexArray(TreeSet<Long> items) {
        List<String> hex = new ArrayList<>();
        for (Long v : items) {
            hex.add("0x" + Long.toHexString(v));
        }
        return jsonStrArray(hex);
    }

    private static String sha256File(String path) throws Exception {
        MessageDigest md = MessageDigest.getInstance("SHA-256");
        try (FileInputStream in = new FileInputStream(path)) {
            byte[] buf = new byte[1 << 20];
            int n;
            while ((n = in.read(buf)) > 0) {
                md.update(buf, 0, n);
            }
        }
        return toHex(md.digest());
    }

    private static String sha256Bytes(byte[] data) throws Exception {
        return toHex(MessageDigest.getInstance("SHA-256").digest(data));
    }

    private static String toHex(byte[] d) {
        StringBuilder b = new StringBuilder();
        for (byte x : d) {
            b.append(String.format("%02x", x & 0xff));
        }
        return b.toString();
    }
}
