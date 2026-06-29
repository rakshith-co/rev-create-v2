# Test Plan: Creatives Model Migration

## 1. Database & Schema Validation
**Goal:** Verify that all creative assets are persisted to the single `creatives` collection with the correct document shape.

- [ ] **Pipeline Execution:** Create a new project and wait for generation.
    - **Check:** Document exists in `creatives` collection (not `images`).
    - **Check:** `source` is set to `"generated"`.
    - **Check:** `metadata` block is fully populated with `subtype` and `size_specs`.
    - **Check:** `generated` block contains `variation_index` and `version: 1`.
    - **Check:** `s3_key` follows the pattern `creatives/{id}.png`.
- [ ] **FB Banner Persistance:** Generate an FB Lead Ad Banner.
    - **Check:** Document exists in `creatives`.
    - **Check:** `project_id` is `null`.
    - **Check:** `metadata.subtype` is `"fb-banner"`.
- [ ] **Static Upload:** Upload a static image via `/api/image/upload`.
    - **Check:** `source` is set to `"uploaded"`.
    - **Check:** `uploaded` block is populated with `original_filename` and `mime_type`.
    - **Check:** `status` is `"uploaded"`.

## 2. API Functional Testing
**Goal:** Ensure all endpoints correctly return the new `CreativeOut` structure and maintain data integrity.

- [ ] **Project Retrieval:** GET `/api/projects/{id}`.
    - **Check:** `images` array contains the new `CreativeOut` shape.
    - **Check:** Verify that the backend helper `_to_out` correctly synthesizes metadata for any legacy documents remaining in the DB.
- [ ] **Image Editing:** POST `/api/images/{id}/edit`.
    - **Check:** The new document has `generated.parent_id` set to the original image ID.
    - **Check:** `generated.version` is incremented.
    - **Check:** `generated.edit_instruction` is preserved.
- [ ] **Size Variants:** POST `/api/images/{id}/size-variants`.
    - **Check:** Multiple documents are created with the same `parent_id`.
    - **Check:** Metadata contains `platform` and `size_label` fields.
- [ ] **Download Logic:** GET `/api/projects/{id}/download`.
    - **Check:** The generated ZIP contains folders for platforms (e.g., `meta/`, `google/`) and follows the new naming convention.

## 3. Frontend UI Verification
**Goal:** Confirm the UI correctly parses and displays the nested data structure.

- [ ] **Main Project Grid:**
    - **Check:** Only the 4 primary variations are displayed (variants and edits should be hidden/accessible only via detail).
    - **Check:** `ImageCard` correctly displays the `variation_index` from the `generated` block.
- [ ] **Image Detail Panel:**
    - **Check:** "Versions" list shows the history of edits for that specific variation.
    - **Check:** "Size Variants" are grouped correctly by platform (Meta/Google).
    - **Check:** Clicking a variant thumbnail updates the main preview image and the "Size Details" specs.
- [ ] **Logs Detail:**
    - **Check:** Images are displayed correctly in the log view, pulling `variation_index` from the new `generated` path.

## 4. Regression & Boundary Tests
- [ ] **Default Subtype:** Create a project with a non-standard dimension (e.g., `500x500`).
    - **Check:** Subtype defaults to `feed-square` as specified in the registry.
- [ ] **Error Handling:** Simulate a failed generation.
    - **Check:** `status` is `"failed"` and `error_message` is populated in the `creatives` document.
- [ ] **Empty States:** View a new project that is still in `"pending"` status.
    - **Check:** UI handles empty `images` arrays or `pending` status without crashing.