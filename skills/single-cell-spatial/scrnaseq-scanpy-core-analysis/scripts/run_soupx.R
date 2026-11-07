# Official SoupX execution; no alternative estimator is substituted.
suppressPackageStartupMessages(library(SoupX))
suppressPackageStartupMessages(library(Matrix))
args <- commandArgs(trailingOnly = TRUE)
stopifnot(length(args) == 3L)
read_10x <- function(directory) {
  open_file <- function(name) {
    plain <- file.path(directory, name)
    if (file.exists(plain)) return(file(plain, "rt"))
    zipped <- paste0(plain, ".gz")
    if (!file.exists(zipped)) stop(paste("Missing input", name))
    gzfile(zipped, "rt")
  }
  read_table <- function(name) {
    con <- open_file(name)
    on.exit(close(con))
    read.delim(con, header = FALSE, stringsAsFactors = FALSE)
  }
  con <- open_file("matrix.mtx")
  counts <- readMM(con)
  close(con)
  features <- read_table(if (file.exists(file.path(directory, "features.tsv")) ||
    file.exists(file.path(directory, "features.tsv.gz"))) "features.tsv" else "genes.tsv")
  cells <- read_table("barcodes.tsv")
  if (ncol(features) >= 3L) {
    keep <- features[[3]] == "Gene Expression"
    counts <- counts[keep, , drop = FALSE]
    features <- features[keep, , drop = FALSE]
  }
  dimnames(counts) <- list(features[[1]], cells[[1]])
  counts
}
raw <- read_10x(args[[1]])
filtered <- read_10x(args[[2]])
stopifnot(identical(rownames(raw), rownames(filtered)))
clusters <- read.csv(file.path(args[[3]], "clusters.csv"), colClasses = "character")
set.seed(0)
channel <- SoupChannel(raw, filtered)
channel <- setClusters(channel, setNames(clusters$cluster, clusters$barcode))
channel <- autoEstCont(channel, doPlot = FALSE)
corrected <- adjustCounts(channel, roundToInt = TRUE)
writeMM(corrected, file.path(args[[3]], "corrected.mtx"))
writeLines(rownames(corrected), file.path(args[[3]], "genes.txt"))
writeLines(colnames(corrected), file.path(args[[3]], "barcodes.txt"))
write.csv(data.frame(rho = channel$metaData[colnames(corrected), "rho"]),
  file.path(args[[3]], "contamination.csv"), row.names = FALSE)
