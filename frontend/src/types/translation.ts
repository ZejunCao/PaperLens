export interface PageTranslation {
  status: 'pending' | 'ready' | 'failed'
  error?: string | null
  sentences: Record<string, string>
}
