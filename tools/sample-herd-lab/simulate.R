suppressMessages(pkgload::load_all("C:/GitHub/vmtrc_coder/vmtrc", quiet = TRUE))
d <- Sys.getenv("OUT", "tools/sample-herd-lab"); unlink(list.files(d, pattern = "[.]csv$", full.names = TRUE))
simulate_herd(d, n_cows = 260, start = "2023-10-29", end = "2026-10-28", seed = 21, farm = "c", feed = TRUE, layout = "commercial")
f <- list.files(d, full.names = TRUE); print(data.frame(file = basename(f), kib = round(file.size(f) / 1024)))
