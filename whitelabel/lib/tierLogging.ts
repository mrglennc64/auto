// Minimal tier-event logging. Required fields only.
// No aggregation, no analytics, no dashboards.

export type TierLogEvent = {
  userId: string;
  numberOfWorks?: number;
  reasonCode: string;
};

export function logTierEvent(event: TierLogEvent): void {
  const entry = {
    timestamp: new Date().toISOString(),
    userId: event.userId,
    numberOfWorks: event.numberOfWorks ?? null,
    reasonCode: event.reasonCode
  };

  // Replace the sink with file/syslog/central log shipper as needed.
  // Keep one entry per blocked or allowed validation. Nothing more.
  // eslint-disable-next-line no-console
  console.log("[Kataloghub Tier]", JSON.stringify(entry));
}
