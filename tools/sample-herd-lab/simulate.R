suppressMessages(pkgload::load_all(Sys.getenv("DAIRY_R"), quiet = TRUE)   # DAIRY_R: the folder of the author's R package)
d <- Sys.getenv("OUT", "tools/sample-herd-lab"); unlink(list.files(d, pattern = "[.]csv$", full.names = TRUE))
simulate_herd(d, n_cows = 260, start = "2023-10-29", end = "2026-10-28", seed = 21, farm = "c", feed = TRUE, layout = "commercial")
f <- list.files(d, full.names = TRUE); print(data.frame(file = basename(f), kib = round(file.size(f) / 1024)))
