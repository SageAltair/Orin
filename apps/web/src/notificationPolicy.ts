export const notificationCategories = [
  "calendar",
  "routines",
  "tasks",
  "projects",
  "opportunities",
  "risks",
  "approvals",
  "jobs",
  "writing",
] as const;
export type NotificationPolicy = {
  enabled: boolean;
  categories: string[];
  persistent: boolean;
  repeat_minutes: number;
  max_repeats: number;
  timezone: string;
  quiet_enabled: boolean;
  quiet_start: string;
  quiet_end: string;
  respect_focus: boolean;
  browser_alerts: boolean;
  sound: boolean;
};
export const defaultNotificationPolicy: NotificationPolicy = {
  enabled: true,
  categories: [...notificationCategories],
  persistent: false,
  repeat_minutes: 15,
  max_repeats: 3,
  timezone: "UTC",
  quiet_enabled: false,
  quiet_start: "22:00",
  quiet_end: "07:00",
  respect_focus: true,
  browser_alerts: false,
  sound: false,
};
let audio: AudioContext | null = null;
export async function playReminderSound() {
  audio ??= new AudioContext();
  await audio.resume();
  const tone = audio.createOscillator();
  const gain = audio.createGain();
  tone.frequency.value = 660;
  gain.gain.setValueAtTime(0.08, audio.currentTime);
  gain.gain.exponentialRampToValueAtTime(0.001, audio.currentTime + 0.3);
  tone.connect(gain);
  gain.connect(audio.destination);
  tone.start();
  tone.stop(audio.currentTime + 0.3);
}
