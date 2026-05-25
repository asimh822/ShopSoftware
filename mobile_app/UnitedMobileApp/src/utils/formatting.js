/**
 * Shared formatting utilities
 */

/**
 * Format a number as PKR with comma separators.
 * e.g. 59500 → "59,500"
 */
export function fmtPKR(value) {
  const n = parseFloat(value);
  if (isNaN(n)) return '0';
  return Math.round(n)
    .toString()
    .replace(/\B(?=(\d{3})+(?!\d))/g, ',');
}

/**
 * Return today's date as DD/MM/YYYY (device local time).
 */
export function todayDDMMYYYY() {
  const d = new Date();
  const dd = String(d.getDate()).padStart(2, '0');
  const mm = String(d.getMonth() + 1).padStart(2, '0');
  const yyyy = d.getFullYear();
  return `${dd}/${mm}/${yyyy}`;
}

/**
 * Validate Pakistani mobile number: exactly 11 digits, starts with 03.
 */
export function isValidPakistaniPhone(phone) {
  return /^03\d{9}$/.test(phone.trim());
}

/**
 * Convert a string to Title Case.
 * e.g. "ahmed khan" → "Ahmed Khan"
 */
export function titleCase(str) {
  if (!str) return '';
  return str
    .trim()
    .split(' ')
    .map(w => (w ? w[0].toUpperCase() + w.slice(1).toLowerCase() : ''))
    .join(' ');
}

/**
 * Shorten IMEI for display: first 8 + "..." + last 4.
 * e.g. "123456789012345" → "12345678...2345"
 */
export function shortImei(imei) {
  if (!imei || imei.length < 12) return imei;
  return `${imei.slice(0, 8)}...${imei.slice(-4)}`;
}
