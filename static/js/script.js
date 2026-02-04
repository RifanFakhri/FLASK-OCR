// script.js (FIXED - dengan button compare)
// Set current year in footer
const yearEl = document.getElementById("currentYear");
if (yearEl) {
  yearEl.textContent = new Date().getFullYear();
}

// Splash screen handling
window.addEventListener("load", function () {
  const yearEl = document.getElementById("currentYear");
  if (yearEl) {
    yearEl.textContent = new Date().getFullYear();
  }

  const splashScreen = document.getElementById("splashScreen");
  const mainContent = document.getElementById("mainContent");

  setTimeout(() => {
    splashScreen.classList.add("hidden");
    setTimeout(() => {
      mainContent.classList.add("show");
    }, 300);
  }, 2500);
});


// File upload handling
const fileInput = document.getElementById("fileInput");
const uploadArea = document.getElementById("uploadArea");
const selectedFile = document.getElementById("selectedFile");
const submitBtn = document.getElementById("submitBtn");
const compareContainer = document.getElementById("compareContainer");
const compareBtn = document.getElementById("compareBtn");

// Click on upload area triggers file input
uploadArea.addEventListener("click", () => {
  fileInput.click();
});

// File input change
fileInput.addEventListener("change", function () {
  if (this.files.length > 0) {
    const file = this.files[0];

    // Validate file type
    if (!file.name.toLowerCase().endsWith(".pdf")) {
      alert("Please select a PDF file only.");
      this.value = "";
      selectedFile.textContent = "No file selected";
      selectedFile.style.color = "#a5b1c2";
      return;
    }

    // Validate file size (10MB max)
    if (file.size > 10 * 1024 * 1024) {
      alert("File size exceeds 10MB limit. Please choose a smaller file.");
      this.value = "";
      selectedFile.textContent = "No file selected";
      selectedFile.style.color = "#a5b1c2";
      return;
    }

    selectedFile.innerHTML = `<strong>Selected:</strong> ${file.name} (${(
      file.size /
      1024 /
      1024
    ).toFixed(2)} MB)`;
    selectedFile.style.color = "#EFB10E";
  } else {
    selectedFile.textContent = "No file selected";
    selectedFile.style.color = "#a5b1c2";
  }
});

// Drag and drop functionality
uploadArea.addEventListener("dragover", (e) => {
  e.preventDefault();
  uploadArea.classList.add("dragover");
});

uploadArea.addEventListener("dragleave", () => {
  uploadArea.classList.remove("dragover");
});

uploadArea.addEventListener("drop", (e) => {
  e.preventDefault();
  uploadArea.classList.remove("dragover");

  if (e.dataTransfer.files.length) {
    const file = e.dataTransfer.files[0];

    // Validate file type
    if (!file.name.toLowerCase().endsWith(".pdf")) {
      alert("Please drop a PDF file only.");
      return;
    }

    // Validate file size (10MB max)
    if (file.size > 10 * 1024 * 1024) {
      alert("File size exceeds 10MB limit. Please choose a smaller file.");
      return;
    }

    fileInput.files = e.dataTransfer.files;
    selectedFile.innerHTML = `<strong>Selected:</strong> ${file.name} (${(
      file.size /
      1024 /
      1024
    ).toFixed(2)} MB)`;
    selectedFile.style.color = "#EFB10E";
  }
});

// Form submission
document
  .getElementById("ocrForm")
  .addEventListener("submit", async function (e) {
    e.preventDefault();

    // Validate file selected
    if (!fileInput.files.length) {
      alert("Please select a PDF file first.");
      return;
    }

    // Disable button and show processing
    const originalText = submitBtn.innerHTML;
    submitBtn.innerHTML =
      '<i class="fas fa-spinner fa-spin"></i> Processing...';
    submitBtn.disabled = true;

    const formData = new FormData(this);

    try {
      const response = await fetch("/upload", {
        method: "POST",
        body: formData,
      });

      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }

      const data = await response.json();

      console.log("FULL RESPONSE:", data);

      // OCR TEXT
        document.getElementById("ocrResult").value =
          data.ocr_text || "No OCR text extracted.";

        // PARSED TABLE
        const thead = document.querySelector("#parsedTable thead");
        const tbody = document.querySelector("#parsedTable tbody");

        // Ambil semua certificate (key angka)
        const certificates = data?.metadata?.certificates ?? [];

        if (certificates.length === 0) {
          tbody.innerHTML =
            '<tr><td colspan="3" class="no-data">No data could be parsed.</td></tr>';
          return;
        }

        // Header
        thead.innerHTML = `
          <tr>
            <th>NO</th>
            <th>FIELD</th>
            <th>VALUE</th>
          </tr>
        `;

        // BODY
        tbody.innerHTML = "";

        // Rows
        certificates.forEach((cert, certIndex) => {
          const fields = cert.extracted_fields || {};

          Object.entries(fields).forEach(([field, value]) => {
            const tr = document.createElement("tr");
            tr.innerHTML = `
              <td>${certIndex + 1}</td>
              <td>${field.toUpperCase().replace(/_/g, " ")}</td>
              <td>${value ?? "-"}</td>
              `;
              tbody.appendChild(tr);
          });
        });

      // ✅ FIX: Tampilkan button compare jika ada parsed data
      const certCount = Object.keys(data).filter(k => !isNaN(k)).length;

      if (certCount > 0) {
      compareContainer.style.display = "flex";
      }

        // Gunakan session_id dari response atau buat fallback
        const sessionId = data.session_id || 'temp_' + Date.now();

        // Simpan data ke localStorage sebagai fallback
        const tempData = {
          metadata: data.metadata,
          ocr_text: "",
          timestamp: new Date().toISOString(),
          certificate_numbers: certificates
            .map(c => c.extracted_fields?.nosert)
            .filter(Boolean)
        };

        // Simpan ke localStorage
        localStorage.setItem("last_ocr_data", JSON.stringify(tempData));

        // Set href untuk tombol compare
        compareBtn.href = `/comparison?session=${sessionId}`;
        compareBtn.innerHTML = `<i class="fas fa-code-compare"></i> Compare with Database (${tempData.certificate_numbers.length || 1} certificate)`;

        console.log("Compare button configured with session:", sessionId);

      // Scroll to results
      document.querySelector(".result-section").scrollIntoView({
        behavior: "smooth",
        block: "start",
      });
    } catch (error) {
      console.error("Error:", error);
      alert("An error occurred while processing the PDF. Please try again.");

      // Reset table
      const tbody = document.querySelector("#parsedTable tbody");
      tbody.innerHTML =
        '<tr><td colspan="3" class="no-data">Error processing document. Please try again.</td></tr>';

      // Clear OCR result
      document.getElementById("ocrResult").value =
        "Error: Could not process the PDF file.";
    } finally {
      // Re-enable button
      submitBtn.innerHTML = originalText;
      submitBtn.disabled = false;
    }
  });

// ✅ FIX: Tambahkan event listener untuk tombol compare
if (compareBtn) {
  compareBtn.addEventListener("click", function(e) {
    // Cek apakah ada data yang diparsing
    const tableRows = document.querySelectorAll("#parsedTable tbody tr");
    if (tableRows.length === 0 ||
        (tableRows.length === 1 && tableRows[0].querySelector(".no-data"))) {
      e.preventDefault();
      alert("Please process a PDF file first before comparing with database.");
    }
  });
}