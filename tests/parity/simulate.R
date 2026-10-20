# Writes the parity fixture with the earlier R version's simulator and intake (DAIRY_R: the folder of that R package).
suppressMessages(pkgload::load_all(Sys.getenv("DAIRY_R"), quiet = TRUE))
out <- Sys.getenv("OUT")
herd_dir <- file.path(out, "herd")
unlink(herd_dir, recursive = TRUE)
simulate_herd(herd_dir, n_cows = 400, seed = 11, farm = "c", feed = TRUE, layout = "commercial")
print(list.files(herd_dir))
print(file.size(list.files(herd_dir, full.names = TRUE)) / 1024)
