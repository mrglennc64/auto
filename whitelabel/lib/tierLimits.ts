// Tier-limit enforcement for Kataloghub.
// Validation-only service. No correction logic, no workflow logic, no dashboards.

export type TierConfig = {
  maxWorksPerValidation: number;
  maxValidationsPerPeriod: number;
  maxCatalogsPerPeriod: number;
};

export type UsageState = {
  validationsThisPeriod: number;
  catalogsThisPeriod: number;
};

export type TierLimitStatus = "allowed" | "blocked";

export type TierLimitCode =
  | "OK"
  | "LIMIT_WORKS"
  | "LIMIT_VALIDATIONS"
  | "LIMIT_CATALOGS";

export type TierLimitResponse = {
  status: TierLimitStatus;
  reason: string;
  code: TierLimitCode;
};

export function validateTierLimits(
  uploadedFile: Buffer | string,
  tierConfig: TierConfig,
  usageState: UsageState
): TierLimitResponse {
  const numberOfWorks = countWorks(uploadedFile);

  if (numberOfWorks > tierConfig.maxWorksPerValidation) {
    return buildResponse(
      "blocked",
      "Valideringen kan inte genomföras. Antalet verk överstiger avtalad nivå.",
      "LIMIT_WORKS"
    );
  }

  if (usageState.validationsThisPeriod >= tierConfig.maxValidationsPerPeriod) {
    return buildResponse(
      "blocked",
      "Valideringsgränsen för perioden är uppnådd. Uppdatering av avtal krävs.",
      "LIMIT_VALIDATIONS"
    );
  }

  if (usageState.catalogsThisPeriod >= tierConfig.maxCatalogsPerPeriod) {
    return buildResponse(
      "blocked",
      "Antalet kataloger överstiger avtalad nivå. Kontakta HeyRoya för justering.",
      "LIMIT_CATALOGS"
    );
  }

  return buildResponse("allowed", "Validering kan genomföras.", "OK");
}

// CSV parser preserving RFC 4180 quoting + Nordic characters; treats either
// comma or semicolon as field separator.
function parseCsvLine(line: string): string[] {
  const out: string[] = [];
  let cur = "";
  let inQuotes = false;
  for (let i = 0; i < line.length; i++) {
    const ch = line[i];
    if (inQuotes) {
      if (ch === '"' && line[i + 1] === '"') { cur += '"'; i++; }
      else if (ch === '"') { inQuotes = false; }
      else { cur += ch; }
    } else {
      if (ch === '"') { inQuotes = true; }
      else if (ch === "," || ch === ";") { out.push(cur); cur = ""; }
      else { cur += ch; }
    }
  }
  out.push(cur);
  return out;
}

// Count the number of distinct works in the uploaded catalog. A "work" is one
// unique title; multiple contributor rows on the same work count once.
export function countWorks(uploadedFile: Buffer | string): number {
  const content =
    typeof uploadedFile === "string"
      ? uploadedFile
      : uploadedFile.toString("utf8");
  if (!content) return 0;

  const lines = content.split(/\r?\n/);
  let i = 0;
  while (i < lines.length && lines[i].trim() === "") i++;
  if (i >= lines.length) return 0;

  const header = parseCsvLine(lines[i]).map((h) => h.trim().toLowerCase());
  const titleCol = header.indexOf("title");
  if (titleCol < 0) return 0;

  const titles = new Set<string>();
  for (i = i + 1; i < lines.length; i++) {
    const line = lines[i];
    if (line.trim() === "") continue;
    const fields = parseCsvLine(line);
    const title = (fields[titleCol] || "").trim();
    if (title !== "") titles.add(title);
  }
  return titles.size;
}

export function buildResponse(
  status: TierLimitStatus,
  reason: string,
  code: TierLimitCode
): TierLimitResponse {
  return { status, reason, code };
}
