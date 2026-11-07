export type AppConfig = { product_name: string; languages: string[]; default_language: string; roles: string[] };

const fallback: AppConfig = { product_name: 'VakeelSevak', languages: ['en', 'ml'], default_language: 'en', roles: [] };

/** The product name and languages come from the API, so a rename needs no app change. */
export async function loadConfig(): Promise<AppConfig> {
  try {
    const r = await fetch('/api/config');
    return r.ok ? ((await r.json()) as AppConfig) : fallback;
  } catch {
    return fallback;
  }
}
