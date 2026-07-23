export type BacktestabilityCode =
  | 'currently_backtestable'
  | 'requires_external_data'
  | 'field_missing'
  | 'mapping_unstable'
  | 'pit_not_verified'

export type CandidateStatus =
  | 'pending'
  | 'validated'
  | 'rejected'
  | 'unavailable'
  | 'backtested'

export interface ResearchSource {
  name: string
  kind: 'field' | 'text' | 'seed' | 'external'
  status: 'available' | 'missing' | 'unverified' | 'reference'
  detail: string
}

export interface ResearchRequest {
  rawClue: string
  hypothesis: string
  signalScope: 'company' | 'industry' | 'macro' | 'mixed'
  economicPhenomenon: string
  observableProxies: string[]
  aShareMapping: string
  sources: ResearchSource[]
  seedReferences: string[]
  target: string
  baseline: string
  dataMode: 'static_demo' | 'synthetic' | 'real'
  backtestability: BacktestabilityCode
  blockingReasons: BacktestabilityCode[]
  draftId: string
  version: 'draft'
  confirmed: false
}

export interface GenerationMaterial {
  knowledgeVersion: string
  dataMode: string
  fields: string[]
  textSources: string[]
  seeds: string[]
  operators: string[]
  hardConstraints: string[]
}

export interface GenerationConfig {
  count: number
  direction: 'both' | 'positive' | 'negative'
  novelty: 'seed_upgrade' | 'cross_source' | 'conservative'
  maxComplexity: number
  allowText: boolean
  currentlyBacktestableOnly: boolean
}

export interface CandidateEvidence {
  factorId: string
  label: string
  status: 'static_precomputed'
  note: string
}

export interface FactorCandidate {
  id: string
  name: string
  category: string
  status: CandidateStatus
  expressionSummary: string
  sourceSummary: string
  fields: string[]
  citations: string[]
  pitRule: string
  synthesis: string
  mechanism: string
  expectedDirection: string
  riskExposures: string[]
  backtestability: BacktestabilityCode
  rejectionReason?: string
  evidence?: CandidateEvidence
}

export interface PreflightItem {
  id: string
  label: string
  status: 'passed' | 'blocked' | 'unverified' | 'external'
  evidence: string
  suggestion?: string
}

export interface WorkbenchScenario {
  request: ResearchRequest
  materials: GenerationMaterial
  config: GenerationConfig
  candidates: FactorCandidate[]
  preflight: PreflightItem[]
}
