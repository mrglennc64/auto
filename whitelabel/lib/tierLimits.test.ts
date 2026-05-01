// Jest test suite for the tier-limit module.

import {
  validateTierLimits,
  countWorks,
  TierConfig,
  UsageState
} from "./tierLimits";

const baseTier: TierConfig = {
  maxWorksPerValidation: 1000,
  maxValidationsPerPeriod: 2,
  maxCatalogsPerPeriod: 1
};

const baseUsage: UsageState = {
  validationsThisPeriod: 0,
  catalogsThisPeriod: 0
};

function makeCsvWithWorks(works: number): string {
  // Each line is a separate unique title — countWorks counts unique titles.
  const header = "title,name,share_percent\n";
  const body = Array.from(
    { length: works },
    (_, i) => `Work ${i + 1},Writer ${i + 1},100`
  ).join("\n");
  return header + body;
}

describe("countWorks", () => {
  test("returns 0 for empty input", () => {
    expect(countWorks("")).toBe(0);
  });

  test("returns 0 when the title column is missing", () => {
    expect(countWorks("foo,bar\n1,2\n")).toBe(0);
  });

  test("counts unique titles only", () => {
    const csv =
      "title,name\n" +
      "Song A,Writer 1\n" +
      "Song A,Writer 2\n" +
      "Song B,Writer 3\n";
    expect(countWorks(csv)).toBe(2);
  });

  test("ignores blank lines", () => {
    const csv = "title,name\n\nSong A,X\n\nSong B,Y\n";
    expect(countWorks(csv)).toBe(2);
  });
});

describe("validateTierLimits", () => {
  test("allows within limits", () => {
    const csv = makeCsvWithWorks(10);
    const res = validateTierLimits(csv, baseTier, baseUsage);
    expect(res.status).toBe("allowed");
    expect(res.code).toBe("OK");
    expect(res.reason).toBe("Validering kan genomföras.");
  });

  test("blocks when works exceed limit", () => {
    const csv = makeCsvWithWorks(1500);
    const res = validateTierLimits(csv, baseTier, baseUsage);
    expect(res.status).toBe("blocked");
    expect(res.code).toBe("LIMIT_WORKS");
    expect(res.reason).toContain("Antalet verk överstiger avtalad nivå");
  });

  test("blocks when validations exceed limit", () => {
    const csv = makeCsvWithWorks(10);
    const usage: UsageState = { ...baseUsage, validationsThisPeriod: 2 };
    const res = validateTierLimits(csv, baseTier, usage);
    expect(res.status).toBe("blocked");
    expect(res.code).toBe("LIMIT_VALIDATIONS");
  });

  test("blocks when catalogs exceed limit", () => {
    const csv = makeCsvWithWorks(10);
    const usage: UsageState = { ...baseUsage, catalogsThisPeriod: 1 };
    const res = validateTierLimits(csv, baseTier, usage);
    expect(res.status).toBe("blocked");
    expect(res.code).toBe("LIMIT_CATALOGS");
  });

  test("WORKS check takes precedence over VALIDATIONS check", () => {
    const csv = makeCsvWithWorks(2000);
    const usage: UsageState = { ...baseUsage, validationsThisPeriod: 5 };
    const res = validateTierLimits(csv, baseTier, usage);
    expect(res.code).toBe("LIMIT_WORKS");
  });

  test("Buffer input is accepted", () => {
    const csv = makeCsvWithWorks(5);
    const res = validateTierLimits(Buffer.from(csv, "utf8"), baseTier, baseUsage);
    expect(res.status).toBe("allowed");
  });
});
