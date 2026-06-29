import React, { useCallback, useEffect, useRef, useState } from "react";
import axios from "axios";
import CreateProjectForm from "./components/CreateProjectForm";
import ProjectDetail from "./components/ProjectDetail";
import ImageDetailPanel from "./components/ImageDetailPanel";
import StatusBadge from "./components/StatusBadge";
import LogsList from "./components/LogsList";
import LogDetail from "./components/LogDetail";
import StandaloneGenerate from "./components/StandaloneGenerate";
import StandaloneUpload from "./components/StandaloneUpload";
import StandaloneSizeVariants from "./components/StandaloneSizeVariants";
import StandaloneEdit from "./components/StandaloneEdit";
import CompositorTest from "./components/CompositorTest";
import { createProject, deleteProject, getLog, getProject, listLogs, listProjects, regenerateProject, stopProject } from "./api";
import { GenerateFormData, LogOut, LogSummary, ProjectOut, ProjectSummary } from "./types";

const EMPTY_FORM: GenerateFormData = {
  product_name: "",
  description: "",
  product_images: [],
  ref_images: [],
  logo_images: [],
  qr_code: null,
  enable_rera: false,
};

export default function App() {
  const [view, setView] = useState<"create" | "project" | "logs" | "test-generate" | "test-upload" | "test-sizes" | "test-edit" | "test-compositor">("test-generate");
  const [provider, setProvider] = useState<"gemini" | "openai">("gemini");
  const [form, setForm] = useState<GenerateFormData>(EMPTY_FORM);
  const [activeProject, setActiveProject] = useState<ProjectOut | null>(null);
  const [projectList, setProjectList] = useState<ProjectSummary[]>([]);
  const [isCreating, setIsCreating] = useState(false);
  const [createError, setCreateError] = useState("");
  const [selectedVariation, setSelectedVariation] = useState<number | null>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const [isLoadingProject, setIsLoadingProject] = useState(false);
  const [isPolling, setIsPolling] = useState(false);
  const [logList, setLogList] = useState<LogSummary[]>([]);
  const [activeLog, setActiveLog] = useState<LogOut | null>(null);

  const refreshLogs = useCallback(() => {
    listLogs().then(setLogList).catch(console.error);
  }, []);

  const refreshList = useCallback(() => {
    listProjects().then(setProjectList).catch(console.error);
  }, []);

  useEffect(() => {
    refreshList();
    refreshLogs();
  }, [refreshList, refreshLogs]);

  const stopPolling = useCallback(() => {
    if (pollRef.current) {
      clearInterval(pollRef.current);
      pollRef.current = null;
    }
    setIsPolling(false);
  }, []);

  const startPolling = useCallback(
    (projectId: string) => {
      stopPolling();
      setIsPolling(true);
      pollRef.current = setInterval(async () => {
        try {
          const proj = await getProject(projectId);
          setActiveProject(proj);
          const projectDone = proj.status === "ready" || proj.status === "failed" || proj.status === "stopped";
          const imagesInProgress = proj.images.some(
            (img) => img.status === "pending" || img.status === "generating" || img.status === "retrying"
          );
          if (projectDone && !imagesInProgress) {
            stopPolling();
            refreshList();
            refreshLogs();
          }
        } catch (e) {
          console.error("Poll error:", e);
        }
      }, 2500);
    },
    [stopPolling, refreshList]
  );

  useEffect(() => () => stopPolling(), [stopPolling]);

  const handleCreate = async () => {
    if (isCreating) return;
    setIsCreating(true);
    setCreateError("");
    try {
      const proj = await createProject(form);
      setActiveProject(proj);
      setView("project");
      setSelectedVariation(null);
      startPolling(proj.id);
      refreshList();
    } catch (e) {
      const msg = axios.isAxiosError(e)
        ? (e.response?.data?.detail ?? e.message)
        : "Failed to create project";
      setCreateError(typeof msg === "string" ? msg : JSON.stringify(msg));
    } finally {
      setIsCreating(false);
    }
  };

  const handleSelectProject = async (id: string) => {
    stopPolling();
    setIsLoadingProject(true);
    setView("project");
    setSelectedVariation(null);
    try {
      const proj = await getProject(id);
      setActiveProject(proj);
      const projectDone = proj.status === "ready" || proj.status === "failed";
      const imagesInProgress = proj.images.some(
        (img) => img.status === "pending" || img.status === "generating" || img.status === "retrying"
      );
      if (!projectDone || imagesInProgress) startPolling(id);
    } catch (e) {
      console.error("Failed to load project:", e);
    } finally {
      setIsLoadingProject(false);
    }
  };

  const handleDeleteProject = async (id: string, e: React.MouseEvent) => {
    e.stopPropagation();
    if (!window.confirm("Delete this project and all its images?")) return;
    try {
      await deleteProject(id);
      if (activeProject?.id === id) {
        stopPolling();
        setActiveProject(null);
        setView("create");
        setSelectedVariation(null);
      }
      refreshList();
    } catch (err) {
      console.error("Delete failed:", err);
    }
  };

  const handleNewProject = () => {
    stopPolling();
    setView("create");
    setForm(EMPTY_FORM);
    setCreateError("");
    setSelectedVariation(null);
  };

  const handleEditSubmit = () => {
    if (activeProject) startPolling(activeProject.id);
  };

  const handleRegenerate = async () => {
    if (!activeProject) return;
    try {
      const proj = await regenerateProject(activeProject.id);
      setActiveProject(proj);
      setSelectedVariation(null);
      startPolling(proj.id);
      refreshList();
    } catch (e) {
      console.error("Regenerate failed:", e);
    }
  };

  const handleViewLogs = () => {
    stopPolling();
    setView("logs");
    setActiveLog(null);
    refreshLogs();
  };

  const handleViewTestGenerate = () => {
    stopPolling();
    setView("test-generate");
    setActiveProject(null);
  };

  const handleViewTestUpload = () => {
    stopPolling();
    setView("test-upload");
    setActiveProject(null);
  };

  const handleOpenSizesTest = () => {
    stopPolling();
    setView("test-sizes");
    setActiveProject(null);
  };

  const handleSelectLog = async (summary: LogSummary) => {
    try {
      const log = await getLog(summary.id);
      setActiveLog(log);
    } catch (e) {
      console.error("Failed to load log:", e);
    }
  };

  const isValid = form.product_name.trim();

  return (
    <div className="min-h-screen bg-gray-950 flex flex-col">
      {/* Header */}
      <header className="flex-shrink-0 border-b border-gray-800 px-5 py-3">
        <div className="flex items-center justify-between">
          <button onClick={handleNewProject} className="flex items-baseline gap-2">
            <span className="text-xl font-bold text-white">revCreate</span>
            <span className="text-xs text-gray-500">AI Ad Creative Generator</span>
          </button>
          <div className="flex items-center gap-2">
            {/* Provider toggle */}
            <div className="flex items-center gap-1 p-1 bg-gray-900 rounded-lg border border-gray-800 mr-2">
              <button
                onClick={() => setProvider("gemini")}
                className={`px-3 py-1 text-xs font-semibold rounded-md transition ${
                  provider === "gemini"
                    ? "bg-violet-600 text-white shadow"
                    : "text-gray-400 hover:text-gray-200"
                }`}
              >
                Gemini
              </button>
              <button
                onClick={() => setProvider("openai")}
                className={`px-3 py-1 text-xs font-semibold rounded-md transition ${
                  provider === "openai"
                    ? "bg-emerald-600 text-white shadow"
                    : "text-gray-400 hover:text-gray-200"
                }`}
              >
                OpenAI
              </button>
            </div>
            <button
              onClick={handleViewTestGenerate}
              className={`px-3 py-1.5 rounded-lg text-xs font-medium transition ${
                view === "test-generate"
                  ? "bg-gray-700 text-white"
                  : "text-gray-400 hover:text-white hover:bg-gray-800"
              }`}
            >
              API Test
            </button>
            <button
              onClick={handleViewTestUpload}
              className={`px-3 py-1.5 rounded-lg text-xs font-medium transition ${
                view === "test-upload"
                  ? "bg-gray-700 text-white"
                  : "text-gray-400 hover:text-white hover:bg-gray-800"
              }`}
            >
              Upload Test
            </button>
            <button
              onClick={handleOpenSizesTest}
              className={`px-3 py-1.5 rounded-lg text-xs font-medium transition ${
                view === "test-sizes"
                  ? "bg-gray-700 text-white"
                  : "text-gray-400 hover:text-white hover:bg-gray-800"
              }`}
            >
              Size Variants
            </button>
            <button
              onClick={() => {
                stopPolling();
                setView("test-edit");
                setActiveProject(null);
              }}
              className={`px-3 py-1.5 rounded-lg text-xs font-medium transition ${
                view === "test-edit"
                  ? "bg-gray-700 text-white"
                  : "text-gray-400 hover:text-white hover:bg-gray-800"
              }`}
            >
              Image Edit
            </button>
            <button
              onClick={() => { stopPolling(); setView("test-compositor"); setActiveProject(null); }}
              className={`px-3 py-1.5 rounded-lg text-xs font-medium transition ${
                view === "test-compositor"
                  ? "bg-gray-700 text-white"
                  : "text-gray-400 hover:text-white hover:bg-gray-800"
              }`}
            >
              Compositor
            </button>
            <button
              onClick={handleViewLogs}
              className={`px-3 py-1.5 rounded-lg text-xs font-medium transition ${
                view === "logs"
                  ? "bg-gray-700 text-white"
                  : "text-gray-400 hover:text-white hover:bg-gray-800"
              }`}
            >
              Logs
            </button>
            {/* {(view === "project" || view === "create") && (
              <button
                onClick={handleNewProject}
                className="px-3 py-1.5 rounded-lg text-xs font-medium
                           bg-violet-600 hover:bg-violet-500 text-white transition"
              >
                + New Project
              </button>
            )} */}
          </div>
        </div>
      </header>

      <div className="flex flex-1 overflow-hidden">
        {/* Sidebar — commented out
        <aside className="w-60 flex-shrink-0 border-r border-gray-800 overflow-y-auto py-4 hidden lg:flex lg:flex-col">
          <p className="px-4 mb-3 text-xs font-semibold text-gray-500 uppercase tracking-wider">
            Projects
          </p>
          {projectList.length === 0 ? (
            <p className="px-4 text-xs text-gray-600">No projects yet</p>
          ) : (
            <ul className="flex-1">
              {projectList.map((p) => (
                <li key={p.id} className="group/item relative">
                  <button
                    onClick={() => handleSelectProject(p.id)}
                    className={[
                      "w-full text-left px-4 py-3 pr-10 hover:bg-gray-800/70 transition border-l-2",
                      activeProject?.id === p.id
                        ? "bg-gray-800 border-violet-500"
                        : "border-transparent",
                    ].join(" ")}
                  >
                    <p className="text-sm text-gray-200 font-medium truncate leading-snug">
                      {p.name}
                    </p>
                    <div className="flex items-center gap-2 mt-1">
                      <StatusBadge status={p.status} />
                      {p.image_count > 0 && (
                        <span className="text-xs text-gray-600">
                          {p.done_count}/{p.image_count}
                        </span>
                      )}
                    </div>
                  </button>
                  <button
                    onClick={(e) => handleDeleteProject(p.id, e)}
                    title="Delete project"
                    className="absolute right-2 top-1/2 -translate-y-1/2
                               opacity-0 group-hover/item:opacity-100 transition
                               p-1.5 rounded-md text-gray-600 hover:text-red-400 hover:bg-gray-800"
                  >
                    <svg className="h-3.5 w-3.5" viewBox="0 0 20 20" fill="currentColor">
                      <path fillRule="evenodd" d="M9 2a1 1 0 00-.894.553L7.382 4H4a1 1 0 000 2v10a2 2 0 002 2h8a2 2 0 002-2V6a1 1 0 100-2h-3.382l-.724-1.447A1 1 0 0011 2H9zM7 8a1 1 0 012 0v6a1 1 0 11-2 0V8zm5-1a1 1 0 00-1 1v6a1 1 0 102 0V8a1 1 0 00-1-1z" clipRule="evenodd" />
                    </svg>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </aside>
        */}

        {/* Main */}
        <main className="flex-1 overflow-y-auto px-6 py-8">
          {view === "test-generate" ? (
            <StandaloneGenerate provider={provider} />
          ) : view === "test-upload" ? (
            <StandaloneUpload />
          ) : view === "test-sizes" ? (
            <StandaloneSizeVariants provider={provider} />
          ) : view === "test-edit" ? (
            <StandaloneEdit provider={provider} />
          ) : view === "test-compositor" ? (
            <CompositorTest />
          ) : view === "logs" ? (
            <div className="max-w-4xl mx-auto space-y-4">
              <div className="flex items-center justify-between">
                <h2 className="text-lg font-semibold text-white">Pipeline Logs</h2>
                <span className="text-xs text-gray-600">{logList.length} runs</span>
              </div>
              <LogsList logs={logList} onSelect={handleSelectLog} />
            </div>
          ) : null
          /* Projects views — commented out
          ) : view === "create" ? (
            <div className="max-w-2xl mx-auto space-y-5">
              <h2 className="text-lg font-semibold text-white">New Project</h2>
              <CreateProjectForm
                data={form}
                onChange={(f, v) => setForm((p) => ({ ...p, [f]: v }))}
              />
              {createError && (
                <div className="bg-red-900/40 border border-red-800 rounded-lg px-4 py-3 text-sm text-red-300">
                  {createError}
                </div>
              )}
              <button
                onClick={handleCreate}
                disabled={!isValid || isCreating}
                className="w-full py-3 rounded-xl font-semibold text-sm transition
                           bg-violet-600 hover:bg-violet-500 text-white
                           disabled:opacity-40 disabled:cursor-not-allowed"
              >
                {isCreating ? (
                  <span className="flex items-center justify-center gap-2">
                    <svg className="animate-spin h-4 w-4" viewBox="0 0 24 24" fill="none">
                      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z" />
                    </svg>
                    Creating project…
                  </span>
                ) : (
                  "Generate Ad Creatives"
                )}
              </button>
            </div>
          ) : isLoadingProject ? (
            <div className="flex items-center justify-center h-64">
              <svg className="animate-spin h-7 w-7 text-violet-500" viewBox="0 0 24 24" fill="none">
                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z" />
              </svg>
            </div>
          ) : activeProject ? (
            <ProjectDetail
              project={activeProject}
              onImageClick={(vi) => setSelectedVariation(vi)}
              isPolling={isPolling}
              onRegenerate={handleRegenerate}
              onStop={async () => {
                stopPolling();
                try {
                  const updated = await stopProject(activeProject.id);
                  setActiveProject(updated);
                  refreshList();
                } catch (e) {
                  console.error("Stop failed:", e);
                }
              }}
            />
          ) : null
          */}
        </main>
      </div>

      {/* Image detail panel */}
      {selectedVariation !== null && activeProject && (
        <ImageDetailPanel
          key={`${activeProject.id}-${selectedVariation}`}
          project={activeProject}
          variationIndex={selectedVariation}
          onClose={() => setSelectedVariation(null)}
          onEditSubmit={handleEditSubmit}
          provider={provider}
        />
      )}

      {/* Log detail panel */}
      {activeLog && (
        <LogDetail
          key={activeLog.id}
          log={activeLog}
          onClose={() => setActiveLog(null)}
          onSaved={(updated) => {
            setActiveLog(updated);
            setLogList((prev) =>
              prev.map((l) =>
                l.id === updated.id ? { ...l, eval: updated.eval } : l
              )
            );
          }}
        />
      )}
    </div>
  );
}
