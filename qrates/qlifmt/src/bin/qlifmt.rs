fn main() -> std::process::ExitCode {
    let args: Vec<_> = std::env::args_os().skip(1).collect();
    let json = qlifmt_engine::support::report::json_requested(&args);
    qlifmt_engine::support::report::emit(qlifmt_engine::run(&args), json)
}
