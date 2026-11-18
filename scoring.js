/* Fantasy Box Office scoring rules. Works in the browser (window.FBO) and Node (module.exports).
 *
 * Defaults: Mexico revenue is always included, and each player's 9 scoring movies are chosen
 * automatically as the highest-revenue legal set from their 12 greenlit movies.
 * The options { includeMexico: false, optimize: false } reproduce the original workbook
 * (used by tests/verify.js to prove the port is faithful).
 */
(function (root) {
  const SUMMER = ["May", "Jun", "Jul", "Aug", "Sep"];
  const LIMITS = { scoring: 9, summer: 5, sequels: 6, maxPerDistributor: 4, minDistributors: 3 };
  const NOT_RELEASED = "Not Released Yet";

  /** North American gross for one movie (US + Mexico), after the Tomatometer penalty. */
  function movieScore(m, data, opts) {
    if (!m) return { raw: 0, us: 0, mex: 0, penalty: 0, net: 0 };
    const us = m.grossDom, mex = opts.includeMexico === false ? 0 : m.grossMex;
    const penalised = m.rt > 0 && m.rt <= data.rtThreshold; // rt of 0 means no score on file
    const raw = us + mex;
    return { raw, us, mex, penalty: penalised ? data.penalty : 0, net: Math.max(raw - (penalised ? data.penalty : 0), 0) };
  }

  const isReleased = k => k.info && k.info.distributor !== NOT_RELEASED;

  /** Rule violations for a set of picks. Returns { issues: [{rule,text,excess}], excess }. */
  function check(sel, rules) {
    const rel = sel.filter(isReleased), issues = [];
    const add = (rule, text, excess) => issues.push({ rule, text, excess });
    const nSeq = rel.filter(k => k.info.franchise).length;
    const nSum = rel.filter(k => SUMMER.includes(k.info.month)).length;
    if (rules.sequels && nSeq > LIMITS.sequels) add("sequels", `${nSeq} sequel/franchise movies (max ${LIMITS.sequels})`, nSeq - LIMITS.sequels);
    if (rules.summer && nSum > LIMITS.summer) add("summer", `${nSum} May–Sep movies (max ${LIMITS.summer})`, nSum - LIMITS.summer);
    if (rules.distributor) {
      const by = {};
      rel.forEach(k => { by[k.info.distributor] = (by[k.info.distributor] || 0) + 1; });
      Object.entries(by).forEach(([d, n]) => { if (n > LIMITS.maxPerDistributor) add("distributor", `${n} movies from ${d} (max ${LIMITS.maxPerDistributor})`, n - LIMITS.maxPerDistributor); });
      const nd = Object.keys(by).length;
      if (rel.length && nd < LIMITS.minDistributors) add("distributor", `Only ${nd} distributors (min ${LIMITS.minDistributors})`, LIMITS.minDistributors - nd);
    }
    return { issues, excess: issues.reduce((a, i) => a + i.excess, 0) };
  }

  /**
   * Choose the scoring set: the largest legal set up to 9 movies, then the highest revenue within that size.
   * (No legal 9 -> best legal 8 -> legal 7 ...). Tries every combination of the picks.
   * Also returns `closest`: the fewest-violations 9, used to explain why a full 9 wasn't possible.
   */
  function chooseScoring(picks, rules) {
    const n = picks.length, top = Math.min(LIMITS.scoring, n);
    const bestLegal = {};                      // size -> { mask, total }
    let closest = null;                        // best attempt at a full set, even if illegal
    for (let mask = 0; mask < (1 << n); mask++) {
      let size = 0; for (let b = mask; b; b &= b - 1) size++;
      if (size > top) continue;
      const sel = picks.filter((_, i) => mask & (1 << i));
      const { excess } = check(sel, rules);
      const total = sel.reduce((a, k) => a + k.net, 0);
      if (excess === 0 && (!bestLegal[size] || total > bestLegal[size].total)) bestLegal[size] = { mask, total };
      if (size === top && (!closest || excess < closest.excess || (excess === closest.excess && total > closest.total))) closest = { mask, excess, total };
    }
    let size = top; while (size > 0 && !bestLegal[size]) size--;
    const pick = size > 0 ? bestLegal[size].mask : 0;
    return { chosen: picks.map((_, i) => !!(pick & (1 << i))), closestMask: closest ? closest.mask : 0 };
  }

  function evaluate(data, opts) {
    opts = Object.assign({ includeMexico: true, optimize: true }, opts);
    const rules = Object.assign({ sequels: true, summer: true, distributor: true }, data.enforce);

    const players = data.players.map(p => {
      const seen = new Set();
      const picks = p.picks.map(k => {
        const key = String(k.movie).toLowerCase();
        const dup = seen.has(key); seen.add(key);                   // a movie greenlit twice only scores once
        const m = data.movies[k.movie];
        const s = dup ? { raw: 0, us: 0, mex: 0, penalty: 0, net: 0 } : movieScore(m, data, opts);
        return { ...k, ...s, submitted: !!k.scoring, movie: k.movie, info: m || null, duplicate: dup };
      });
      const sel = opts.optimize ? chooseScoring(picks, rules) : { chosen: picks.map(k => k.submitted), closestMask: 0 };
      picks.forEach((k, i) => { k.scoring = sel.chosen[i]; });

      const scoring = picks.filter(k => k.scoring), submitted = picks.filter(k => k.submitted);
      const { issues } = check(scoring, rules);
      // Why a full 9 wasn't possible (empty when the player fields a legal 9).
      const fullSize = Math.min(LIMITS.scoring, picks.length);
      const blockers = opts.optimize && scoring.length < fullSize ? check(picks.filter((_, i) => sel.closestMask & (1 << i)), rules).issues : [];
      const rel = scoring.filter(isReleased), byDist = {};
      rel.forEach(k => { byDist[k.info.distributor] = (byDist[k.info.distributor] || 0) + 1; });
      const sum = a => a.reduce((t, k) => t + k.net, 0);

      return {
        name: p.name, employed: p.employed, picks, issues, blockers, scoringCount: scoring.length,
        gross: sum(picks),                 // all 12 greenlit movies
        adjusted: sum(scoring),            // the 9 scoring movies
        submittedAdjusted: sum(submitted), // the 9 picked by hand in the original workbook
        withRevenue: picks.filter(k => k.net > 0).length,
        sequels: rel.filter(k => k.info.franchise).length,
        summer: rel.filter(k => SUMMER.includes(k.info.month)).length,
        distributors: byDist,
      };
    });

    const rank = key => {
      const sorted = [...players].sort((a, b) => b[key] - a[key] || a.name.localeCompare(b.name));
      sorted.forEach((p, i) => { p[key + "Rank"] = i + 1; });
    };
    rank("gross"); rank("adjusted");
    // Prize standing: employed players, by total of their counted movies.
    players.filter(p => p.employed).sort((a, b) => b.adjusted - a.adjusted)
      .forEach((p, i) => { p.prizeRank = i + 1; });

    const movies = {};
    data.players.forEach(p => p.picks.forEach(k => {
      (movies[k.movie] = movies[k.movie] || { name: k.movie, greenlights: 0, scoringPicks: 0 });
      movies[k.movie].greenlights++;
    }));
    players.forEach(p => p.picks.forEach(k => { if (k.scoring) movies[k.movie].scoringPicks++; }));
    const movieList = Object.values(movies).map(m => {
      const info = data.movies[m.name];
      return { ...m, info: info || null, ...movieScore(info, data, opts) };
    }).sort((a, b) => b.greenlights - a.greenlights || b.raw - a.raw || a.name.localeCompare(b.name));

    return { players, movies: movieList };
  }

  const api = { evaluate, movieScore, check, LIMITS, SUMMER };
  if (typeof module !== "undefined" && module.exports) module.exports = api; else root.FBO = api;
})(typeof window !== "undefined" ? window : globalThis);
