fn main() -> std::process::ExitCode {
    let args: Vec<_> = std::env::args_os().skip(1).collect();
    let json = qlinties_engine::report::json_requested(&args);
    qlinties_engine::report::emit(qlinties_engine::qlinties::run(&args), json)
}
