/**
 * AIPR Pro 前端类型定义
 *
 * 数据来源：electron/main.cjs 的 IPC handler 返回值
 * 契约依据：electron/preload.cjs 暴露的 window.aiprDesktop
 */

// ---------- 任务 ----------

export type TaskStatus =
  | "ended"
  | "idle"
  | "running"
  | "paused"
  | "completed"
  | "failed"
  | "waiting"
  | "unknown";

export interface ShopState {
  checkedAt?: string;
  label: string;
  port: string;
  status: string;
}

export interface TaskRules {
  threshold: number;
  exclusions: string[];
  weights: {
    persona: number;
    content: number;
    sales: number;
    scene: number;
    price: number;
  };
}

export interface CollectionStrategy {
  sourceType?: string;
  brief?: string;
  viralExamples?: string;
  category?: string;
  creatorLevels?: number[];
  minimumFollowers?: number;
  maximumFollowers?: number;
  minimumMonthlySales?: number;
  contentType?: string;
  requireContact?: boolean;
  activeShops?: string[];
  keywords?: string[];
  exclusions?: string[];
  targetCount?: number;
  sourceDiscoveryMode?: string;
  [key: string]: unknown;
}

export interface Task {
  brandRevisions?: {version:number;createdAt:string;fingerprint:string;config:Record<string,unknown>}[];
  id: string;
  name: string;
  targetCount: number;
  collected: number;
  processed: number;
  plainContacts: number;
  wechat: number;
  phone: number;
  remaining: number;
  contactDelayMs: number;
  status: TaskStatus;
  rules?: TaskRules;
  outputDir: string;
  deliveryPath: string;
  queuePath: string;
  originalWorkbookPath: string;
  originalExport?: {path:string;deliveryPath:string;sourceWorkbookPath:string;createdAt:string};
  shops?: Record<string, ShopState>;
  collectionStrategy?: CollectionStrategy;
  updatedAt?: string;
  endedAt?: string;
  endedReason?: string;
}

// ---------- 达人 ----------

export interface Creator {
  canonicalTaskCreatorId?: string;
  contactCorrectionCreatorId?: string;
  id?: string;
  identity?: string;
  nickname: string;
  douyinId?: string;
  douyinHomepage?: string;
  buyinHomepage?: string;
  fans?: number;
  gender?: number;
  city?: string;
  talentLevel?: string;
  category?: string;
  monthlySalesLow?: number;
  monthlySalesHigh?: number;
  monthlySalesLowerBound?: number;
  monthlySalesDisplay?: string;
  videoCount30d?: number;
  mainSaleType?: string;
  price?: number;
  wechat?: string;
  phone?: string;
  plainContact?: string;
  contactStatus?: string;
  score?: number;
  decision?: string;
  reason?: string;
  shop?: string;
  [key: string]: unknown;
}

// ---------- 实时流 ----------

export interface RealtimeFlowMetrics {
  candidates?: number;
  suitable?: number;
  contactRevealing?: number;
  plaintext?: number;
  listed?: number;
  [key: string]: number | undefined;
}

export interface RealtimeFlow {
  available: boolean;
  updatedAt?: string;
  metrics: RealtimeFlowMetrics;
}

// ---------- 平台自检 ----------

export interface PlatformCheck {
  key: string;
  label: string;
  passed: boolean;
  detail: string;
}

export interface PlatformReadiness {
  platform: string;
  arch: string;
  supported: boolean;
  python: string;
  browser: string;
  documents: string;
  checks: PlatformCheck[];
  ready: boolean;
}

// ---------- 交付中心 ----------

export interface DeliveryArtifacts {
  finalJson?: string;
  standardXlsx?: string;
  originalXlsx?: string;
  robotNdjson?: string;
  robotBatchJson?: string;
  handoffManifest?: string;
  [key: string]: string | undefined;
}

export interface RoiFunnel {
  candidates: number;
  verified: number;
  qualified: number;
  revealed: number;
  delivered: number;
  rates: {
    verify_rate: string;
    qualify_rate: string;
    reveal_rate: string;
    deliver_rate: string;
    end_to_end_rate: string;
  };
}

export interface RoiContacts {
  with_contact: number;
  phone: number;
  wechat: number;
  only_phone: number;
  only_wechat: number;
  both_phone_and_wechat: number;
  contact_rate: string;
}

export interface RoiJev {
  enabled: number;
  coverage_rate: string;
  routes: Record<string, number>;
  supported_rate: string;
  conflict_rate: string;
  uncertain_rate: string;
  confidence: { count: number; min: number | null; max: number | null; avg: number | null };
  backends: Record<string, number>;
  cloud_errors: number;
}

export interface RoiReport {
  generated_at?: string;
  funnel?: RoiFunnel;
  jev?: RoiJev;
  contacts?: RoiContacts;
  levels?: Record<string, number>;
  categories?: Record<string, number>;
  risk?: Record<string, number>;
  roi?: {
    budget?: number;
    estimated_spent?: number;
    budget_remaining?: number | null;
    budget_utilization?: string | null;
    cost_per_revealed_contact?: number | null;
    cost_per_delivered?: number | null;
  };
  throughput?: {
    elapsed_minutes: number;
    reveals_per_minute: number;
    seconds_per_reveal: number | null;
  } | null;
  error?: string;
}

export interface DeliveryCenter {
  validation?: {ok:boolean;stale?:boolean;checkedAt:string;rowCount:number;queueCount:number;errors:string[];scope?:string;files:{key:string;sha256:string}[]} | null;
  available: boolean;
  artifacts: DeliveryArtifacts;
  metrics?: Record<string, number>;
  roi?: RoiReport;
  [key: string]: unknown;
}

// ---------- 外联 ----------

export interface OutreachBatch {
  id: string;
  status: string;
  validCount?: number;
  missingCount?: number;
  duplicateCount?: number;
  selectedCount?: number;
  createdAt?: string;
  [key: string]: unknown;
}

export interface OutreachState {
  batches?: OutreachBatch[];
  integrationPaths?: Record<string, string>;
  [key: string]: unknown;
}

// ---------- 运行历史 ----------

export interface RunHistoryEntry {
  recordedAt?: string;
  message?: string;
  id?: string;
  startedAt?: string;
  finishedAt?: string;
  status?: string;
  candidateCount?: number;
  listedCount?: number;
  [key: string]: unknown;
}

// ---------- Bootstrap ----------

export interface Bootstrap {
  savedWechatRepairCount?:number;
  historicalWechatRepairCount?:number;
  savedEvidenceReview?: {contact_review_status?:string;status:string;remaining_count?:number;updated_at:string;records:{identity:string;screenshots:string[];content_status:string;manual_review_required:boolean;contact_verification:{reachability:string;channels:Record<string,string>}}[]};
  contactCorrections?: {creatorId:string;before:Record<string,string>;after:Record<string,string>;source:string;reason:string;revision:number;recordedAt:string}[];
  contactRevisionPending?:boolean;
  runtimeMetrics?: {available:boolean;scope:string;runs?:number;elapsedMs?:number;effectiveMs?:number;cooldownMs?:number;unknownMs?:number;newCreators?:number;interruptions?:number;netPerHour?:number|null};
  appVersion?: string;
  maintenance?: {busy:boolean;message:string;files:number;bytes:number;lastBackup:string};
  reviewRecords?: {creatorId:string;note:string;disposition:string;recordedAt:string;revision:number;admissionChanged:boolean}[];
  creatorLibrary?: { creators: Creator[]; batches: { id: string; name: string; count: number; status?: string; deliveryPath?:string; baselinePath?:string }[] };
  qwenStatus?: {provider:string;configured:boolean;model:string;purpose:string;credentialChanged:boolean};
  jevStatus?: { connectionTest?: {ok:boolean;message:string;checkedAt:string;model?:string;elapsedMs:number;usage?:{input_tokens?:number;output_tokens?:number}}; credentialProtection?: string; enabled: boolean; configured: boolean; decisionMode: boolean; model?: string; usage?: { calls: number; inputTokens: number | null; outputTokens: number | null; inputCoverage: number; outputCoverage: number; firstAt: string | null; lastAt: string | null; lastModel: string | null; invalidRows: number; readError: boolean; attempts?: number; failures?: number; retries?: number; averageLatencyMs?: number | null; writeError?: boolean; accountStatus?: { recordedAt: string; outcome: string; httpStatus: number | null } | null; byTask?: Record<string, {attempts:number;calls:number;failures:number;retries:number;inputTokens:number|null;outputTokens:number|null}>; byDate?: Record<string, {attempts:number;calls:number;failures:number;retries:number;inputTokens:number|null;outputTokens:number|null}>; balance: null; billedAmount: null } };
  task: Task;
  tasks: Task[];
  currentBatch?:{id:string;baselineCount:number;newCount:number;baselinePath:string}|null;
  creators: Creator[];
  candidateCreators: Creator[];
  realtimeFlow: RealtimeFlow;
  integrationPaths: Record<string, string>;
  deliveryCenter: DeliveryCenter;
  platformReadiness: PlatformReadiness;
  runHistory: RunHistoryEntry[];
  outreachBatches: OutreachBatch[];
}

// ---------- Worker 事件 ----------

export interface WorkerEvent {
  status: string;
  shop?: string;
  message?: string;
  candidate_count?: number;
  discovered_count?: number;
  suitable_count?: number;
  listed_count?: number;
  processed?: number;
  total?: number;
  [key: string]: unknown;
}

export interface ShopBrowserEvent {
  shop?: string;
  action?: string;
  url?: string;
  [key: string]: unknown;
}
