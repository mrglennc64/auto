// Express middleware: enforce tier limits before the actual validation
// handler runs. Either full validation or no validation — never partial.

import { Request, Response, NextFunction } from "express";
import {
  validateTierLimits,
  countWorks,
  TierConfig,
  UsageState
} from "./tierLimits";
import { logTierEvent } from "./tierLogging";

export function tierLimitsMiddleware(
  getTierConfig: (req: Request) => TierConfig,
  getUsageState: (req: Request) => Promise<UsageState>
) {
  return async (req: Request, res: Response, next: NextFunction) => {
    try {
      const file = (req as Request & { file?: { buffer: Buffer } }).file;
      if (!file) {
        return res
          .status(400)
          .json({ message: "Ingen fil mottagen för validering." });
      }

      const tierConfig = getTierConfig(req);
      const usageState = await getUsageState(req);

      const result = validateTierLimits(file.buffer, tierConfig, usageState);

      const userId = String(
        ((req as Request & { user?: { id?: string | number } }).user?.id) ?? "unknown"
      );

      logTierEvent({
        userId,
        numberOfWorks: countWorks(file.buffer),
        reasonCode: result.code
      });

      if (result.status === "blocked") {
        return res
          .status(403)
          .json({ message: result.reason, code: result.code });
      }

      return next();
    } catch (_err) {
      return res
        .status(500)
        .json({ message: "Tekniskt fel vid kontroll av valideringsnivå." });
    }
  };
}
