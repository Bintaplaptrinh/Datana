"use client";

import {
  ChangeEvent,
  FormEvent,
  ReactNode,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import {
  Alert,
  Box,
  Button,
  Chip,
  CssBaseline,
  Divider,
  FormControl,
  InputLabel,
  MenuItem,
  Paper,
  Select,
  Slider,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  TextField,
  ThemeProvider,
  ToggleButton,
  ToggleButtonGroup,
  Typography,
  createTheme,
} from "@mui/material";
import styles from "./page.module.css";
import { API_ROOT, dataApi } from "@/lib/api";
import { parseCsv, serializeCsv } from "@/lib/csv";
import {
  ContextMode,
  CrawlRequest,
  JobRecord,
  PipelineNode,
  ProviderInfo,
  SourceName,
  Status,
  WranglerFileContent,
  WranglerFileRecord,
} from "@/lib/types";

type View = "wrangler" | "crawl";
type PanelId = "configure" | "pipeline" | "runs" | "logs" | "storage";
type Field = { id: number; key: string; value: string };

const defaultPanels: PanelId[] = ["configure", "pipeline", "runs", "logs", "storage"];
const panelLabels: Record<PanelId, string> = {
  configure: "New crawl",
  pipeline: "Pipeline DAG",
  runs: "Task status",
  logs: "Execution logs",
  storage: "Context and output",
};

const theme = createTheme({
  palette: {
    mode: "light",
    primary: { main: "#ffffff", contrastText: "#15171b" },
    secondary: { main: "#355df5", contrastText: "#ffffff" },
    success: { main: "#2caa8c" },
    error: { main: "#e15c75" },
    text: { primary: "#16191f", secondary: "#626b78" },
    background: { default: "#dbe5e5", paper: "rgba(255,255,255,.53)" },
  },
  typography: {
    fontFamily: '"Google Sans Flex", "Google Sans", Arial, sans-serif',
    h2: { fontSize: "clamp(2.35rem, 5vw, 4rem)", lineHeight: 1.03, fontWeight: 650 },
    h5: { fontWeight: 600 },
    h6: { fontWeight: 600 },
    button: { textTransform: "none", fontWeight: 600 },
  },
  shape: { borderRadius: 20 },
  components: {
    MuiButton: {
      styleOverrides: {
        root: {
          borderRadius: 999,
          paddingInline: 20,
          "&.MuiButton-containedPrimary": {
            boxShadow: "0 12px 26px rgba(82, 93, 115, .15), inset 0 1px 0 rgba(255,255,255,.9)",
          },
        },
      },
    },
    MuiChip: { styleOverrides: { root: { borderRadius: 999 } } },
    MuiOutlinedInput: {
      styleOverrides: { root: { background: "rgba(255,255,255,.46)", borderRadius: 16 } },
    },
    MuiTextField: { defaultProps: { size: "small" } },
    MuiFormControl: { defaultProps: { size: "small" } },
    MuiToggleButton: { styleOverrides: { root: { borderRadius: 999 } } },
  },
});

function Symbol({ children }: { children: string }) {
  return <span className="material-symbols-rounded">{children}</span>;
}

function statusColor(status: Status | "pending") {
  if (status === "succeeded") return "success";
  if (status === "failed") return "error";
  if (status === "running") return "secondary";
  return "default";
}

function StatusChip({ status }: { status: Status | "pending" }) {
  return <Chip size="small" color={statusColor(status)} variant="outlined" label={status} />;
}

interface PanelProps {
  id: PanelId;
  children: ReactNode;
  wide?: boolean;
  onMove: (dragged: PanelId, destination: PanelId) => void;
}

function GlassPanel({ id, children, wide, onMove }: PanelProps) {
  return (
    <Paper
      component="section"
      onDragOver={(event) => event.preventDefault()}
      onDrop={(event) => {
        event.preventDefault();
        const dragged = event.dataTransfer.getData("panel") as PanelId;
        if (dragged) onMove(dragged, id);
      }}
      className={`${styles.panel} ${wide ? styles.wide : ""}`}
      elevation={0}
    >
      <Stack direction="row" sx={{ alignItems: "center", justifyContent: "space-between", mb: 2 }}>
        <Typography variant="h6">{panelLabels[id]}</Typography>
        <span
          className={styles.dragHandle}
          aria-label={`Drag ${panelLabels[id]}`}
          draggable
          onDragStart={(event) => event.dataTransfer.setData("panel", id)}
        >
          <Symbol>drag_indicator</Symbol>
        </span>
      </Stack>
      {children}
    </Paper>
  );
}

function fieldsToMetadata(fields: Field[]): Record<string, string> {
  return Object.fromEntries(
    fields.filter((field) => field.key.trim()).map((field) => [field.key.trim(), field.value.trim()]),
  );
}

function metadataToFields(metadata: Record<string, string>): Field[] {
  const entries = Object.entries(metadata);
  return entries.length
    ? entries.map(([key, value], index) => ({ id: index + 1, key, value: String(value) }))
    : [{ id: 1, key: "desc", value: "" }];
}

function MetadataFields({ fields, onChange }: { fields: Field[]; onChange: (fields: Field[]) => void }) {
  const change = (id: number, property: "key" | "value", value: string) =>
    onChange(fields.map((field) => (field.id === id ? { ...field, [property]: value } : field)));
  return (
    <Stack spacing={1}>
      {fields.map((field) => (
        <Stack direction="row" spacing={1} key={field.id}>
          <TextField
            label="Metadata key"
            value={field.key}
            onChange={(event) => change(field.id, "key", event.target.value)}
            sx={{ flex: "0 0 38%" }}
          />
          <TextField
            label="Value"
            value={field.value}
            onChange={(event) => change(field.id, "value", event.target.value)}
            fullWidth
          />
          <Button
            className={styles.squareButton}
            aria-label="Remove metadata field"
            onClick={() => onChange(fields.filter((item) => item.id !== field.id))}
          >
            <Symbol>remove</Symbol>
          </Button>
        </Stack>
      ))}
      <Button
        variant="text"
        startIcon={<Symbol>add</Symbol>}
        onClick={() => onChange([...fields, { id: Date.now(), key: "", value: "" }])}
        sx={{ alignSelf: "flex-start" }}
      >
        Add metadata
      </Button>
    </Stack>
  );
}

function ConfigurePanel({
  providers,
  busy,
  onSubmit,
}: {
  providers: ProviderInfo[];
  busy: boolean;
  onSubmit: (request: CrawlRequest) => Promise<void>;
}) {
  const [source, setSource] = useState<SourceName>("tiktok");
  const [url, setUrl] = useState("");
  const [limit, setLimit] = useState(200);
  const [mode, setMode] = useState<ContextMode>("global");
  const [fields, setFields] = useState<Field[]>([
    { id: 1, key: "desc", value: "" },
    { id: 2, key: "topic", value: "" },
  ]);
  const selected = providers.find((provider) => provider.key === source);

  async function submit(event: FormEvent) {
    event.preventDefault();
    await onSubmit({
      source,
      target_url: url,
      max_comments: limit,
      context_mode: mode,
      metadata: fieldsToMetadata(fields),
    });
  }

  return (
    <Box component="form" onSubmit={submit}>
      <Stack spacing={2}>
        <FormControl fullWidth>
          <InputLabel id="provider">Data source</InputLabel>
          <Select
            labelId="provider"
            label="Data source"
            value={source}
            onChange={(event) => setSource(event.target.value as SourceName)}
          >
            {providers.map((provider) => (
              <MenuItem
                key={provider.key}
                value={provider.key}
                disabled={provider.availability !== "ready"}
              >
                {provider.label} {provider.availability !== "ready" ? "(connector required)" : ""}
              </MenuItem>
            ))}
          </Select>
        </FormControl>
        <Typography color="text.secondary" variant="body2">
          {selected?.accepts ?? "Loading source adapters..."}
        </Typography>
        <TextField
          label="Content URL"
          placeholder="https://www.tiktok.com/@creator/video/..."
          value={url}
          onChange={(event) => setUrl(event.target.value)}
          required
          fullWidth
        />
        <Box>
          <Stack direction="row" sx={{ justifyContent: "space-between" }}>
            <Typography variant="body2" color="text.secondary">
              Maximum comments
            </Typography>
            <Typography variant="body2">{limit}</Typography>
          </Stack>
          <Slider
            color="secondary"
            value={limit}
            min={10}
            max={2000}
            step={10}
            onChange={(_, value) => setLimit(value as number)}
          />
        </Box>
        <ToggleButtonGroup
          exclusive
          fullWidth
          value={mode}
          onChange={(_, value: ContextMode | null) => value && setMode(value)}
        >
          <ToggleButton value="global">Global context</ToggleButton>
          <ToggleButton value="pairwise">Pairwise context</ToggleButton>
        </ToggleButtonGroup>
        <Divider />
        <MetadataFields fields={fields} onChange={setFields} />
        <Button variant="contained" size="large" type="submit" disabled={busy || !url}>
          {busy ? "Queueing..." : "Start crawl"}
        </Button>
      </Stack>
    </Box>
  );
}

function PipelinePanel({ job }: { job?: JobRecord }) {
  const emptyNodes: PipelineNode[] = [
    { id: "fetch", label: "Collect source comments", status: "pending", detail: "" },
    { id: "normalize", label: "Clean and normalize records", status: "pending", detail: "" },
    { id: "context", label: "Apply metadata context", status: "pending", detail: "" },
    { id: "export", label: "Write JSON output", status: "pending", detail: "" },
  ];
  return (
    <Stack spacing={1.3}>
      {(job?.nodes ?? emptyNodes).map((node, index, nodes) => (
        <Box key={node.id} className={styles.dagRow}>
          <Box className={`${styles.dagDot} ${styles[node.status]}`} />
          <Box sx={{ flex: 1 }}>
            <Stack direction="row" spacing={1} sx={{ justifyContent: "space-between" }}>
              <Typography variant="body2" sx={{ fontWeight: 600 }}>
                {node.label}
              </Typography>
              <StatusChip status={node.status} />
            </Stack>
            {node.detail && (
              <Typography variant="caption" color="text.secondary">
                {node.detail}
              </Typography>
            )}
          </Box>
          {index < nodes.length - 1 && <Box className={styles.dagLine} />}
        </Box>
      ))}
      <Typography variant="caption" color="text.secondary">
        {job ? `Selected run ${job.id}` : "Select or start a run to follow the DAG."}
      </Typography>
    </Stack>
  );
}

function RunsPanel({
  jobs,
  selectedId,
  onSelect,
  onRetry,
}: {
  jobs: JobRecord[];
  selectedId?: string;
  onSelect: (id: string) => void;
  onRetry: (id: string) => Promise<void>;
}) {
  return (
    <Stack spacing={1} className={styles.scrollArea}>
      {!jobs.length && (
        <Typography variant="body2" color="text.secondary">
          No crawl runs yet. A new job will appear here immediately.
        </Typography>
      )}
      {jobs.map((job) => (
        <Box
          className={`${styles.runRow} ${selectedId === job.id ? styles.selected : ""}`}
          role="button"
          tabIndex={0}
          onClick={() => onSelect(job.id)}
          key={job.id}
        >
          <Stack direction="row" sx={{ justifyContent: "space-between", alignItems: "center" }}>
            <Box>
              <Typography variant="body2" sx={{ fontWeight: 600 }}>
                {job.request.source.toUpperCase()} / {job.id}
              </Typography>
              <Typography variant="caption" color="text.secondary">
                {new Date(job.created_at).toLocaleString()} | {job.record_count} records
              </Typography>
            </Box>
            <StatusChip status={job.status} />
          </Stack>
          {job.status === "failed" && (
            <Button
              size="small"
              variant="text"
              startIcon={<Symbol>refresh</Symbol>}
              onClick={(event) => {
                event.stopPropagation();
                void onRetry(job.id);
              }}
            >
              Retry
            </Button>
          )}
        </Box>
      ))}
    </Stack>
  );
}

function LogsPanel({ job }: { job?: JobRecord }) {
  return (
    <Box className={styles.console}>
      {(job?.logs ?? []).map((line) => (
        <Typography component="div" className={styles.consoleLine} key={`${line.timestamp}${line.message}`}>
          <span>{new Date(line.timestamp).toLocaleTimeString()}</span>
          <strong className={styles[line.level]}>{line.level}</strong>
          {line.message}
        </Typography>
      ))}
      {!job && <Typography color="text.secondary">Waiting for a selected run.</Typography>}
    </Box>
  );
}

function StoragePanel({
  job,
  onUpdate,
}: {
  job?: JobRecord;
  onUpdate: (metadata: Record<string, string>, mode: ContextMode) => Promise<void>;
}) {
  const [fields, setFields] = useState<Field[]>(() => metadataToFields(job?.request.metadata ?? {}));
  const [mode, setMode] = useState<ContextMode>(() => job?.request.context_mode ?? "global");
  if (!job) {
    return <Typography color="text.secondary">Select a completed run to edit context or export data.</Typography>;
  }
  return (
    <Stack spacing={2}>
      <Typography variant="body2" color="text.secondary">
        Edit metadata; saved changes rematerialize completed output for Wrangler.
      </Typography>
      <ToggleButtonGroup
        exclusive
        size="small"
        fullWidth
        value={mode}
        onChange={(_, value: ContextMode | null) => value && setMode(value)}
      >
        <ToggleButton value="global">Global</ToggleButton>
        <ToggleButton value="pairwise">Pairwise</ToggleButton>
      </ToggleButtonGroup>
      <MetadataFields fields={fields} onChange={setFields} />
      <Stack direction="row" spacing={1}>
        <Button
          variant="contained"
          onClick={() => void onUpdate(fieldsToMetadata(fields), mode)}
          disabled={job.status === "running"}
        >
          Save context
        </Button>
        {job.status === "succeeded" && (
          <Button component="a" href={`${API_ROOT}/jobs/${job.id}/download`} variant="outlined">
            Download JSON
          </Button>
        )}
      </Stack>
    </Stack>
  );
}

function suggestedEditName(file: WranglerFileRecord): string {
  const period = file.name.lastIndexOf(".");
  const stem = period >= 0 ? file.name.slice(0, period) : file.name;
  const extension = period >= 0 ? file.name.slice(period) : ".txt";
  return `${stem}_edited${extension}`;
}

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function CsvEditor({ content, onChange }: { content: string; onChange: (content: string) => void }) {
  const rows = useMemo(() => parseCsv(content), [content]);
  const headers = rows[0] ?? [""];
  const body = rows.slice(1);

  function updateCell(row: number, column: number, value: string) {
    const next = rows.map((values) => [...values]);
    while (next[row].length <= column) next[row].push("");
    next[row][column] = value;
    onChange(serializeCsv(next));
  }

  function addColumn() {
    const next = rows.length ? rows.map((row) => [...row, ""]) : [["column_1"]];
    next[0][next[0].length - 1] = `column_${next[0].length}`;
    onChange(serializeCsv(next));
  }

  function addRow() {
    const width = Math.max(headers.length, 1);
    onChange(serializeCsv([...rows, Array.from({ length: width }, () => "")]));
  }

  return (
    <>
      <Stack direction="row" spacing={1} className={styles.tableActions}>
        <Button variant="contained" size="small" onClick={addRow} startIcon={<Symbol>add</Symbol>}>
          Row
        </Button>
        <Button variant="contained" size="small" onClick={addColumn} startIcon={<Symbol>add</Symbol>}>
          Column
        </Button>
      </Stack>
      <TableContainer className={styles.dataTable}>
        <Table stickyHeader size="small">
          <TableHead>
            <TableRow>
              {headers.map((cell, column) => (
                <TableCell key={`header-${column}`}>
                  <input
                    className={styles.cellInput}
                    aria-label={`Header ${column + 1}`}
                    value={cell}
                    onChange={(event) => updateCell(0, column, event.target.value)}
                  />
                </TableCell>
              ))}
            </TableRow>
          </TableHead>
          <TableBody>
            {body.map((row, rowIndex) => (
              <TableRow key={`row-${rowIndex}`}>
                {headers.map((_, column) => (
                  <TableCell key={`cell-${rowIndex}-${column}`}>
                    <input
                      className={styles.cellInput}
                      aria-label={`Row ${rowIndex + 1}, column ${column + 1}`}
                      value={row[column] ?? ""}
                      onChange={(event) => updateCell(rowIndex + 1, column, event.target.value)}
                    />
                  </TableCell>
                ))}
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </TableContainer>
    </>
  );
}

function DataWrangler({ onError }: { onError: (message: string) => void }) {
  const uploadInput = useRef<HTMLInputElement>(null);
  const [files, setFiles] = useState<WranglerFileRecord[]>([]);
  const [current, setCurrent] = useState<WranglerFileContent>();
  const [draft, setDraft] = useState("");
  const [editName, setEditName] = useState("");
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<string>();

  const openFile = useCallback(
    async (fileId: string) => {
      setBusy(true);
      try {
        const file = await dataApi.wranglerFile(fileId);
        setCurrent(file);
        setDraft(file.content);
        setEditName(suggestedEditName(file.file));
      } catch (reason) {
        onError(reason instanceof Error ? reason.message : "Unable to load data file.");
      } finally {
        setBusy(false);
      }
    },
    [onError],
  );

  const refreshFiles = useCallback(
    async (preferredId?: string) => {
      try {
        const available = await dataApi.wranglerFiles();
        setFiles(available);
        const chosen = preferredId ?? current?.file.id ?? available[0]?.id;
        if (chosen) await openFile(chosen);
      } catch (reason) {
        onError(reason instanceof Error ? reason.message : "Unable to list stored data.");
      }
    },
    [current, onError, openFile],
  );

  useEffect(() => {
    let active = true;
    void dataApi
      .wranglerFiles()
      .then(async (available) => {
        if (!active) return;
        setFiles(available);
        if (available[0]) await openFile(available[0].id);
      })
      .catch((reason: Error) => onError(reason.message));
    return () => {
      active = false;
    };
  }, [onError, openFile]);

  async function upload(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file) return;
    setBusy(true);
    setNotice(undefined);
    try {
      const uploaded = await dataApi.uploadWranglerFile(file.name, await file.text());
      await refreshFiles(uploaded.file.id);
      setNotice(`${uploaded.file.name} uploaded and opened.`);
    } catch (reason) {
      onError(reason instanceof Error ? reason.message : "Unable to upload file.");
    } finally {
      setBusy(false);
    }
  }

  async function saveEdit() {
    if (!current) return;
    setBusy(true);
    setNotice(undefined);
    try {
      const edited = await dataApi.saveWranglerEdit(current.file.id, editName, draft);
      await refreshFiles(edited.file.id);
      setNotice(`Saved edited file: ${edited.file.name}`);
    } catch (reason) {
      onError(reason instanceof Error ? reason.message : "Unable to save changes.");
    } finally {
      setBusy(false);
    }
  }

  function formatJson() {
    try {
      setDraft(`${JSON.stringify(JSON.parse(draft), null, 2)}\n`);
      setNotice("JSON formatted in the editor. Save to persist it.");
    } catch {
      onError("The current JSON is invalid and cannot be formatted.");
    }
  }

  return (
    <section className={styles.wranglerLayout}>
      <Paper className={`${styles.panel} ${styles.editorPanel}`} elevation={0}>
        <Stack direction="row" sx={{ justifyContent: "space-between", alignItems: "center", mb: 2 }}>
          <Box>
            <Typography className={styles.sectionLabel}>DATA WRANGLER</Typography>
            <Typography variant="h5">Editor preview</Typography>
          </Box>
          {current && (
            <Stack direction="row" spacing={1}>
              <Chip variant="outlined" label={current.file.format.toUpperCase()} />
              <Chip variant="outlined" label={current.file.origin} />
            </Stack>
          )}
        </Stack>
        {!current && (
          <Box className={styles.emptyEditor}>
            <Symbol>upload_file</Symbol>
            <Typography variant="h6">Choose or upload a data file</Typography>
            <Typography color="text.secondary">
              JSON, JSONL and text open as raw editable content. CSV opens as a table.
            </Typography>
          </Box>
        )}
        {current?.file.format === "csv" && <CsvEditor content={draft} onChange={setDraft} />}
        {current && current.file.format !== "csv" && (
          <TextField
            className={styles.rawEditor}
            multiline
            minRows={18}
            maxRows={26}
            fullWidth
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
            placeholder="Raw file content"
          />
        )}
      </Paper>

      <Paper className={`${styles.panel} ${styles.optionsPanel}`} elevation={0}>
        <Stack direction="row" sx={{ justifyContent: "space-between", alignItems: "center", mb: 2 }}>
          <Box>
            <Typography className={styles.sectionLabel}>SOURCE AND EDIT OPTIONS</Typography>
            <Typography variant="h6">Data controls</Typography>
          </Box>
          <Button variant="contained" onClick={() => uploadInput.current?.click()} disabled={busy}>
            <Symbol>upload</Symbol>&nbsp; Upload file
          </Button>
          <input
            ref={uploadInput}
            hidden
            type="file"
            accept=".csv,.json,.jsonl,.txt,text/plain,text/csv,application/json"
            onChange={(event) => void upload(event)}
          />
        </Stack>
        <Stack spacing={2}>
          <FormControl fullWidth>
            <InputLabel id="stored-file">System files</InputLabel>
            <Select
              labelId="stored-file"
              label="System files"
              value={current?.file.id ?? ""}
              onChange={(event) => void openFile(event.target.value)}
              displayEmpty
            >
              {!files.length && <MenuItem value="">No saved or crawled files available</MenuItem>}
              {files.map((file) => (
                <MenuItem key={file.id} value={file.id}>
                  {file.name} / {file.origin} / {formatSize(file.size)}
                </MenuItem>
              ))}
            </Select>
          </FormControl>
          <Typography variant="body2" color="text.secondary">
            Select files crawled by this system or previously edited here. Upload supports CSV, JSON,
            JSONL and raw text only.
          </Typography>
          <Divider />
          {current && (
            <>
              <Stack direction="row" spacing={1} className={styles.optionPills}>
                {current.file.format === "json" && (
                  <Button variant="contained" onClick={formatJson}>
                    Format JSON
                  </Button>
                )}
                <Chip label={current.file.relative_path} variant="outlined" />
              </Stack>
              <TextField
                fullWidth
                label="Edited output name"
                value={editName}
                onChange={(event) => setEditName(event.target.value)}
                helperText="Saved into storage/wrangler/edited; keep the original file extension."
              />
              <Button variant="contained" size="large" onClick={() => void saveEdit()} disabled={busy}>
                {busy ? "Working..." : "Save edited copy"}
              </Button>
            </>
          )}
          {notice && <Alert severity="success">{notice}</Alert>}
        </Stack>
      </Paper>
    </section>
  );
}

function Hero({ view, setView, crawls, files }: { view: View; setView: (view: View) => void; crawls: number; files: number }) {
  return (
    <section className={styles.hero}>
      <Box className={styles.heroCopy}>
        <Typography className={styles.sectionLabel}>DATA PIPELINE WORKSPACE</Typography>
        <Typography variant="h2">
          Make social data
          <br />
          ready to use.
        </Typography>
        <Typography className={styles.heroText}>
          Crawl public conversations, inspect raw datasets and refine metadata through a quiet,
          flexible workspace.
        </Typography>
        <Stack direction="row" spacing={1.2}>
          <Button variant="contained" size="large" onClick={() => setView("wrangler")}>
            Open Wrangler
          </Button>
          <Button variant="outlined" size="large" onClick={() => setView("crawl")}>
            Crawl data
          </Button>
        </Stack>
      </Box>
      <Box className={styles.heroVisual}>
        <Box className={styles.orb} />
        <Box className={styles.visualSheet}>
          <Typography variant="caption">Current studio</Typography>
          <Typography variant="h5">{view === "wrangler" ? "Data Wrangler" : "Crawl Studio"}</Typography>
          <Stack direction="row" spacing={1} className={styles.statRow}>
            <Box><strong>{files}</strong><span>files</span></Box>
            <Box><strong>{crawls}</strong><span>runs</span></Box>
          </Stack>
        </Box>
      </Box>
    </section>
  );
}

export default function Home() {
  const [view, setView] = useState<View>("wrangler");
  const [providers, setProviders] = useState<ProviderInfo[]>([]);
  const [jobs, setJobs] = useState<JobRecord[]>([]);
  const [fileCount, setFileCount] = useState(0);
  const [selectedId, setSelectedId] = useState<string>();
  const [panels, setPanels] = useState<PanelId[]>(defaultPanels);
  const [error, setError] = useState<string>();
  const [submitting, setSubmitting] = useState(false);
  const [connected, setConnected] = useState(false);

  const reportError = useCallback((message: string) => setError(message), []);

  const refresh = useCallback(async () => {
    try {
      const [currentJobs, files] = await Promise.all([dataApi.jobs(), dataApi.wranglerFiles()]);
      setJobs(currentJobs);
      setFileCount(files.length);
      setSelectedId((current) => current ?? currentJobs[0]?.id);
      setConnected(true);
    } catch (reason) {
      setConnected(false);
      setError(reason instanceof Error ? reason.message : "Unable to connect to API.");
    }
  }, []);

  useEffect(() => {
    const saved = window.localStorage.getItem("dashboard-panels");
    const restoreTimer = saved
      ? window.setTimeout(() => setPanels(JSON.parse(saved) as PanelId[]), 0)
      : undefined;
    return () => {
      if (restoreTimer) window.clearTimeout(restoreTimer);
    };
  }, []);

  useEffect(() => {
    void dataApi.providers().then(setProviders).catch((reason: Error) => setError(reason.message));
    const initialTimer = window.setTimeout(() => void refresh(), 0);
    const timer = window.setInterval(() => void refresh(), 3500);
    return () => {
      window.clearTimeout(initialTimer);
      window.clearInterval(timer);
    };
  }, [refresh]);

  const selected = useMemo(() => jobs.find((job) => job.id === selectedId), [jobs, selectedId]);

  function movePanel(dragged: PanelId, destination: PanelId) {
    if (dragged === destination) return;
    setPanels((current) => {
      const next = current.filter((panel) => panel !== dragged);
      next.splice(next.indexOf(destination), 0, dragged);
      window.localStorage.setItem("dashboard-panels", JSON.stringify(next));
      return next;
    });
  }

  async function createJob(request: CrawlRequest) {
    setSubmitting(true);
    setError(undefined);
    try {
      const job = await dataApi.create(request);
      setSelectedId(job.id);
      await refresh();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Could not create the crawl.");
    } finally {
      setSubmitting(false);
    }
  }

  async function retryJob(id: string) {
    setError(undefined);
    try {
      const job = await dataApi.retry(id);
      setSelectedId(job.id);
      await refresh();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Could not retry this crawl.");
    }
  }

  async function updateMetadata(metadata: Record<string, string>, mode: ContextMode) {
    if (!selected) return;
    setError(undefined);
    try {
      await dataApi.updateMetadata(selected.id, metadata, mode);
      await refresh();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Could not update metadata.");
    }
  }

  const content: Record<PanelId, ReactNode> = {
    configure: <ConfigurePanel providers={providers} busy={submitting} onSubmit={createJob} />,
    pipeline: <PipelinePanel job={selected} />,
    runs: <RunsPanel jobs={jobs} selectedId={selectedId} onSelect={setSelectedId} onRetry={retryJob} />,
    logs: <LogsPanel job={selected} />,
    storage: (
      <StoragePanel
        key={`${selected?.id ?? "none"}-${selected?.updated_at ?? "new"}`}
        job={selected}
        onUpdate={updateMetadata}
      />
    ),
  };

  return (
    <ThemeProvider theme={theme}>
      <CssBaseline />
      <main className={styles.shell}>
        <Paper className={styles.frame} elevation={0}>
          <header className={styles.header}>
            <Typography className={styles.brand}>Data Engineer Tool</Typography>
            <nav className={styles.nav}>
              <Button className={view === "wrangler" ? styles.activeNav : ""} onClick={() => setView("wrangler")}>
                Wrangler
              </Button>
              <Button className={view === "crawl" ? styles.activeNav : ""} onClick={() => setView("crawl")}>
                Crawl Studio
              </Button>
              <Button disabled>Sources</Button>
              <Button disabled>Exports</Button>
            </nav>
            <Chip
              icon={<Symbol>{connected ? "cloud_done" : "cloud_off"}</Symbol>}
              label={connected ? "Connected" : "Offline"}
              className={styles.statusPill}
            />
          </header>
          <Hero view={view} setView={setView} crawls={jobs.length} files={fileCount} />
        </Paper>

        {error && (
          <Alert severity="error" onClose={() => setError(undefined)} className={styles.alert}>
            {error}
          </Alert>
        )}

        {view === "wrangler" ? (
          <DataWrangler onError={reportError} />
        ) : (
          <Box className={styles.grid}>
            {panels.map((panel) => (
              <GlassPanel
                id={panel}
                key={panel}
                wide={panel === "logs" || panel === "storage"}
                onMove={movePanel}
              >
                {content[panel]}
              </GlassPanel>
            ))}
          </Box>
        )}
      </main>
    </ThemeProvider>
  );
}
