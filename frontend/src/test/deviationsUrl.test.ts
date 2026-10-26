import { describe, expect, it } from "vitest";

import {
  apiParams,
  DEFAULT_PERIOD,
  deviationsHref,
  DRILL_ORDER,
  LENS_OF,
  nextLevel,
  parseDeviationState,
  toSearchParams,
  type DeviationUrlState,
} from "../lib/deviationsUrl";

const parse = (qs: string) => parseDeviationState(new URLSearchParams(qs));
const queryOf = (href: string) => href.split("?")[1] ?? "";

/** Ten normalised states (exactly as `parseDeviationState` returns them). */
const STATES: DeviationUrlState[] = [
  { cmp: "fc_pl", medida: "revenue", path: {} },
  { cmp: "fc_pl", medida: "units", periodo: "t1", path: { region: "Nordeste" } },
  {
    cmp: "fc_tg",
    medida: "revenue",
    path: { region: "Sul", channel: "Varejo Moderno" },
    nivel: "series",
    sel: "Rede Horizonte Supermercados|SKU-10101",
  },
  { cmp: "ac_pl", medida: "revenue", periodo: "2026-03", path: {}, nivel: "category", de: "realizado" },
  {
    cmp: "ac_fc",
    medida: "revenue",
    path: { customer: "Litoral Market", sku: "SKU-10101" },
    nivel: "series",
    serie: "Litoral Market|SKU-10101",
    de: "precisao",
  },
  { cmp: "ac_cs", medida: "revenue", path: {}, nivel: "champion", causa: "promocao" },
  {
    cmp: "ac_fc",
    medida: "revenue",
    periodo: "2026-01",
    path: { region: "Norte" },
    nivel: "series_type",
    causa: "volatilidade",
  },
  { cmp: "fc_pl", medida: "revenue", path: { brand: "Marca Sol & Mar" }, nivel: "customer" },
  {
    cmp: "fc_tg",
    medida: "units",
    path: {
      region: "Sul",
      channel: "Atacado",
      customer: "Cliente & Filhos",
      category: "Bebidas",
      sku: "SKU-1",
    },
    de: "meta",
  },
  {
    cmp: "fc_pl",
    medida: "revenue",
    periodo: "t4",
    path: { customer: "Rede Horizonte Supermercados" },
    nivel: "category",
    sel: "Bebidas",
    de: "gap",
  },
];

describe("deviationsUrl · constants (spec §2.3.2)", () => {
  it("derives the lens from the comparison and has one default period per comparison", () => {
    expect(LENS_OF).toEqual({
      fc_pl: "plano",
      fc_tg: "plano",
      ac_pl: "plano",
      ac_fc: "previsao",
      ac_cs: "previsao",
    });
    expect(DEFAULT_PERIOD).toEqual({ fc_pl: "h", fc_tg: "h", ac_pl: "u12m", ac_fc: "bt", ac_cs: "bt" });
    expect(DRILL_ORDER).toEqual(["region", "channel", "customer", "category", "sku"]);
  });

  it("nextLevel is the first DRILL_ORDER key absent from the path, else series", () => {
    expect(nextLevel({})).toBe("region");
    expect(nextLevel({ region: "Sul" })).toBe("channel");
    expect(nextLevel({ customer: "Litoral Market" })).toBe("region");
    expect(nextLevel({ brand: "Marca A" })).toBe("region");
    expect(
      nextLevel({
        region: "Sul",
        channel: "Atacado",
        customer: "Litoral Market",
        category: "Bebidas",
        sku: "SKU-1",
      }),
    ).toBe("series");
  });
});

describe("deviationsUrl · round trip", () => {
  it.each(STATES.map((s, i) => [i + 1, s] as const))("state %i: parse(toSearchParams(s)) == s", (_, s) => {
    expect(parseDeviationState(toSearchParams(s))).toEqual(s);
  });

  it.each(STATES.map((s, i) => [i + 1, s] as const))("state %i survives the href (encoding)", (_, s) => {
    const href = deviationsHref(s);
    expect(href.startsWith("/app/desvios")).toBe(true);
    expect(parse(queryOf(href))).toEqual(s);
  });

  it("the ten states are normalised (parse is idempotent on them)", () => {
    for (const s of STATES)
      expect(parse(toSearchParams(parse(toSearchParams(s).toString())).toString())).toEqual(s);
  });
});

describe("deviationsUrl · toSearchParams", () => {
  it("omits every default", () => {
    expect(toSearchParams({ cmp: "fc_pl", medida: "revenue", path: {} }).toString()).toBe("");
    expect(toSearchParams({}).toString()).toBe("");
    expect(
      toSearchParams({ cmp: "fc_pl", periodo: "h", path: { region: "Sul" }, nivel: "channel" }).toString(),
    ).toBe("region=Sul");
    expect(toSearchParams({ cmp: "ac_pl", periodo: "u12m" }).toString()).toBe("cmp=ac_pl");
    expect(toSearchParams({ cmp: "ac_fc", periodo: "bt", medida: "revenue" }).toString()).toBe(
      "lente=previsao&cmp=ac_fc",
    );
  });

  it("writes keys in the contract order", () => {
    const q = toSearchParams({
      de: "gap",
      serie: "A|B",
      causa: "promocao",
      sel: "X",
      nivel: "champion",
      path: { sku: "S", brand: "B", category: "C", customer: "Cu", channel: "Ch", region: "R" },
      medida: "units",
      periodo: "2026-02",
      cmp: "ac_cs",
    });
    expect([...q.keys()]).toEqual([
      "lente",
      "cmp",
      "periodo",
      "medida",
      "region",
      "channel",
      "customer",
      "category",
      "brand",
      "sku",
      "nivel",
      "sel",
      "causa",
      "serie",
      "de",
    ]);
  });

  it("deviationsHref encodes spaces as %20 and has no '?' without params", () => {
    expect(deviationsHref({})).toBe("/app/desvios");
    expect(deviationsHref({ path: { customer: "Litoral Market" } })).toBe(
      "/app/desvios?customer=Litoral%20Market",
    );
    expect(
      deviationsHref({
        cmp: "fc_pl",
        periodo: "h",
        nivel: "customer",
        path: { region: "Sul" },
        de: "resumo",
      }),
    ).toBe("/app/desvios?region=Sul&nivel=customer&de=resumo");
  });
});

describe("deviationsUrl · parseDeviationState", () => {
  it("falls back to defaults on invalid values", () => {
    expect(parse("cmp=xyz&medida=kg&periodo=u12m&de=capitulo9&nivel=planeta")).toEqual({
      cmp: "fc_pl",
      medida: "revenue",
      path: {},
    });
  });

  it('"lente=previsao" without cmp means ac_fc; an explicit cmp wins', () => {
    expect(parse("lente=previsao").cmp).toBe("ac_fc");
    expect(parse("lente=previsao&cmp=fc_tg").cmp).toBe("fc_tg");
    expect(parse("lente=plano").cmp).toBe("fc_pl");
  });

  it("validates the period against the comparison", () => {
    expect(parse("periodo=T2").periodo).toBe("t2");
    expect(parse("periodo=2026-12").periodo).toBe("2026-12");
    expect(parse("periodo=2026-13").periodo).toBeUndefined();
    expect(parse("cmp=ac_pl&periodo=h").periodo).toBeUndefined();
    expect(parse("cmp=ac_fc&periodo=t1").periodo).toBeUndefined();
    expect(parse("cmp=ac_fc&periodo=bt").periodo).toBeUndefined(); // the default is omitted
  });

  it("accepts a month given as an ISO day (chart rows) and writes it as YYYY-MM", () => {
    expect(parse("periodo=2026-12-01").periodo).toBe("2026-12");
    expect(toSearchParams({ cmp: "ac_pl", periodo: "2026-03-01" }).toString()).toBe(
      "cmp=ac_pl&periodo=2026-03",
    );
    expect(apiParams({ cmp: "fc_pl", medida: "revenue", path: {}, periodo: "2026-12-01" }).period).toBe(
      "2026-12",
    );
    expect(parse("periodo=2026-13-01").periodo).toBeUndefined();
  });

  it("drops levels and filters that do not apply", () => {
    expect(parse("region=Sul&nivel=region").nivel).toBeUndefined(); // already in the path
    expect(parse("nivel=champion").nivel).toBeUndefined(); // Previsão only
    expect(parse("lente=previsao&nivel=champion").nivel).toBe("champion");
    expect(parse("causa=promocao").causa).toBeUndefined(); // Previsão only
    expect(parse("region=%20&channel=Atacado").path).toEqual({ channel: "Atacado" });
  });
});

describe("deviationsUrl · apiParams", () => {
  it("maps the URL state to the /api/deviations/* query", () => {
    expect(apiParams(parse("lente=previsao&medida=units&region=Sul"))).toEqual({
      cmp: "ac_fc",
      period: "bt",
      measure: "revenue",
      level: "channel",
      region: "Sul",
    });
    expect(apiParams(parse("cmp=fc_tg&periodo=t3&medida=units&nivel=customer"))).toEqual({
      cmp: "fc_tg",
      period: "t3",
      measure: "units",
      level: "customer",
    });
  });
});
