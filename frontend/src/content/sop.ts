/**
 * Standard Operating Procedures shown on the SOP page.
 *
 * This is SAMPLE content describing the field-sales workflow in this app.
 * Replace or extend it with Sam IT's approved procedures — the page renders
 * whatever is in SOPS, no code changes needed.
 */

export interface SopStep {
  title: string;
  details?: string[];
}

export interface SopSection {
  heading: string;
  steps: SopStep[];
}

export interface Sop {
  id: string;
  title: string;
  summary: string;
  owner: string;
  version: string;
  lastReviewed: string; // YYYY-MM-DD
  audience: string;
  sample?: boolean;
  sections: SopSection[];
}

export const SOPS: Sop[] = [
  {
    id: "field-sales-meeting",
    title: "Field Sales Meeting",
    summary: "How to prepare for, run and follow up on an in-person prospect meeting.",
    owner: "Sales Manager",
    version: "0.1 (sample)",
    lastReviewed: "2026-10-08",
    audience: "Salespeople, Sales Admins",
    sample: true,
    sections: [
      {
        heading: "1. The day before",
        steps: [
          {
            title: "Review tomorrow's route",
            details: [
              "Open My Route and check every stop has a verified location (green check).",
              "If a stop shows Needs Review, fix the address or tell your admin before you leave.",
            ],
          },
          {
            title: "Confirm the meeting with the contact",
            details: ["Call or email the contact to confirm the time.", "Mark the meeting Confirmed once they reply."],
          },
        ],
      },
      {
        heading: "2. Before you walk in (10 minutes)",
        steps: [
          {
            title: "Read the Business Overview",
            details: [
              "Open the meeting and read the Business Overview: what they do, footprint, and Why this may matter.",
              "Check the sources. Treat anything marked Limited public info as unconfirmed and ask about it in the meeting.",
            ],
          },
          {
            title: "Plan two or three questions",
            details: [
              "Base them on the IT signals in the overview, such as multiple locations, compliance or remote staff.",
              "Don't assume their current setup. Ask about it.",
            ],
          },
        ],
      },
      {
        heading: "3. During the meeting",
        steps: [
          {
            title: "Ask for consent before recording",
            details: [
              "Tell everyone present that you'd like to record the meeting for notes, and get a clear yes.",
              "If anyone declines, don't record. Take written notes instead.",
            ],
          },
          {
            title: "Start the meeting and the recording",
            details: [
              "Tap Start meeting, then Start Recording.",
              "Keep the phone on the table between speakers.",
              "Use Pause for off-the-record moments.",
            ],
          },
          {
            title: "Cover the essentials",
            details: [
              "Current IT setup and pain points.",
              "Number of users, devices and locations.",
              "Compliance needs.",
              "Who makes the decision, and the timeline.",
            ],
          },
        ],
      },
      {
        heading: "4. Right after the meeting",
        steps: [
          {
            title: "Stop the recording before you leave the room",
            details: [
              "Tap Stop and wait for Uploading to finish.",
              "If the upload fails, tap Retry upload. If it fails again, tap Download audio so the recording is kept.",
            ],
          },
          {
            title: "Complete the meeting",
            details: [
              "Add short notes: needs, objections and next step.",
              "Set the next follow-up date, then tap Complete meeting.",
            ],
          },
        ],
      },
      {
        heading: "5. Same day follow-up",
        steps: [
          {
            title: "Review the transcript",
            details: [
              "When Transcript ready appears, skim it and correct anything wrong in your notes.",
              "Speakers are labelled Speaker 1, 2 and so on, not by name.",
            ],
          },
          {
            title: "Prepare the proposal if there's interest",
            details: ["Open Quote Builder from the sidebar and start the proposal while the details are fresh."],
          },
          {
            title: "Update the CRM",
            details: [
              "Log the outcome and next step in Bigin.",
              "Company and contact changes made in Bigin sync to Meetings Manager automatically.",
            ],
          },
        ],
      },
      {
        heading: "Data handling",
        steps: [
          {
            title: "Recordings and transcripts are confidential",
            details: [
              "Don't download audio to personal devices or share transcripts outside Sam IT.",
              "Delete a recording if the prospect asks you to.",
            ],
          },
        ],
      },
    ],
  },
];
