// node tests/verify.js
// 1) Legacy mode (no Mexico, hand-picked 9) must reproduce the original workbook's scores and ranks.
// 2) Then prints what the new defaults (Mexico always in, best legal 9 chosen automatically) change.
const { evaluate } = require("../scoring.js");
const data = require("../data/data.json");
const exp = require("./workbook_expected.json");
const money = n => "$" + Math.round(n).toLocaleString("en-US");

const legacy = evaluate(data, { includeMexico: false, optimize: false });
let bad = 0;
for (const p of legacy.players) {
  const e = exp[p.name]; const diffs = [];
  if (p.adjusted !== e.adjusted) diffs.push(`adjusted ${p.adjusted} vs workbook ${e.adjusted}`);
  if (p.gross !== e.gross) diffs.push(`gross ${p.gross} vs workbook ${e.gross}` + (p.name === "Adam Eller" ? " (known workbook bug: Engine!F6 sums unpenalised gross)" : ""));
  if (p.adjustedRank !== e.adjRank) diffs.push(`adjRank ${p.adjustedRank} vs ${e.adjRank}`);
  if (diffs.length && !(diffs.length === 1 && p.name === "Adam Eller")) { bad++; console.log("MISMATCH " + p.name + ": " + diffs.join(" | ")); }
}
console.log(bad ? `${bad} unexpected mismatch(es)` : "Legacy mode matches the original workbook (except the known Engine!F6 bug).");

const now = evaluate(data);
console.log("\nNew defaults — standings by best legal 9 (US + Mexico):");
[...now.players].sort((a, b) => a.adjustedRank - b.adjustedRank).forEach(p => {
  const gain = p.adjusted - p.submittedAdjusted;
  console.log(`${String(p.adjustedRank).padStart(2)}. ${p.name.padEnd(22)} ${money(p.adjusted).padStart(15)}  counted:${p.scoringCount} prize:${p.prizeRank || "-"}  vs hand-picked 9: ${gain >= 0 ? "+" : ""}${money(gain)}${p.blockers.length ? "  (no legal 9: " + p.blockers.map(i => i.text).join("; ") + ")" : ""}`);
});
