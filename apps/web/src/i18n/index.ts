// Add a language by adding one file here and listing its code in the API LANGUAGES setting.
import { en } from './en';
import { ml } from './ml';

export type Messages = Record<keyof typeof en, string>;
const catalogs: Record<string, Messages> = { en, ml };

export function t(lang: string, key: keyof Messages): string {
  return (catalogs[lang] ?? en)[key] ?? en[key];
}
export const languageNames: Record<string, string> = { en: 'English', ml: 'മലയാളം' };
