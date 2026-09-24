use rusb::{DeviceHandle, GlobalContext};
use std::{env, fs, path::Path, thread::sleep, time::Duration};

const VID: u16 = 0x1c75;
const PID_MF1: u16 = 0xaf80;
const PID_MF1_MSD: u16 = 0xaf82;
const PID_MF2: u16 = 0xaf90;
const PID_MF4: u16 = 0xaf70;
const SYSFS_PATH: &str = "/dev/minifuse_cmd";

#[derive(Clone, Copy)]
enum Model {
    MiniFuse1,
    MiniFuse2,
    MiniFuse4,
}

impl Model {
    fn from_pid(pid: u16) -> Option<Model> {
        match pid {
            PID_MF1 | PID_MF1_MSD => Some(Model::MiniFuse1),
            PID_MF2 => Some(Model::MiniFuse2),
            PID_MF4 => Some(Model::MiniFuse4),
            _ => None,
        }
    }

    fn name(self) -> &'static str {
        match self {
            Model::MiniFuse1 => "MiniFuse 1",
            Model::MiniFuse2 => "MiniFuse 2",
            Model::MiniFuse4 => "MiniFuse 4",
        }
    }

    fn targets(self) -> &'static str {
        match self {
            Model::MiniFuse4 => "'inst1', 'inst2' or '48v'",
            _ => "'inst', '48v' or 'monitor'",
        }
    }
}

// wValue is (feature << 8) | channel
fn parse_selector(model: Model, target: &str) -> Option<u16> {
    match model {
        Model::MiniFuse4 => match target {
            "inst" | "inst1" => Some(0x0000),
            "inst2" => Some(0x0001),
            "48v" => Some(0x0300),
            _ => None,
        },
        _ => match target {
            "inst" => Some(0x0000),
            "48v" => Some(0x0400),
            "monitor" => Some(0x0500),
            _ => None,
        },
    }
}

fn main() {
    let args: Vec<String> = env::args().collect();

    let pairs_args = &args[1..];

    if pairs_args.is_empty() || pairs_args.len() % 2 != 0 {
        eprintln!("Usage: mf-cli <target> <on|off> [<target> <on|off> ...]");
        eprintln!("Targets:");
        eprintln!("  MiniFuse 1/2: inst, 48v, monitor");
        eprintln!("  MiniFuse 4:   inst1, inst2, 48v");
        eprintln!("Examples:");
        eprintln!("  mf-cli inst on");
        eprintln!("  mf-cli 48v on monitor off");
        eprintln!("  mf-cli inst1 on inst2 off 48v on");
        std::process::exit(1);
    }

    let model = match detect_model() {
        Some(m) => m,
        None => {
            eprintln!("Error: No MiniFuse device found.");
            std::process::exit(1);
        }
    };

    let mut commands: Vec<(u16, bool, &str)> = Vec::new();
    for chunk in pairs_args.chunks(2) {
        let target = chunk[0].as_str();
        let state = chunk[1].as_str();

        let selector = match parse_selector(model, target) {
            Some(s) => s,
            None => {
                eprintln!(
                    "Error: Unknown target '{}' for {}. Use {}.",
                    target,
                    model.name(),
                    model.targets()
                );
                std::process::exit(1);
            }
        };

        if state != "on" && state != "off" {
            eprintln!(
                "Error: Unknown state '{}' for target '{}'. Use 'on' or 'off'.",
                state, target
            );
            std::process::exit(1);
        }

        let enable = state == "on";
        commands.push((selector, enable, target));
    }

    // 1. Try using the seamless Kernel Module first
    if Path::new(SYSFS_PATH).exists() {
        println!(
            "[*] Kernel module detected. Sending commands to {} seamlessly...",
            model.name()
        );
        for (selector, enable, target) in &commands {
            let cmd = format!("{:04x} {}", selector, if *enable { 1 } else { 0 });
            match fs::write(SYSFS_PATH, &cmd) {
                Ok(_) => {
                    println!(
                        "[+] {} toggled {}.",
                        target,
                        if *enable { "ON" } else { "OFF" }
                    );
                }
                Err(e) => {
                    eprintln!(
                        "[-] Failed to write command for {} to kernel module: {}",
                        target, e
                    );
                }
            }
            // Small delay to ensure the hardware processes sequential commands
            sleep(Duration::from_millis(50));
        }
        println!("[*] All commands sent via kernel module.");
        return;
    }

    // 2. Fallback to userspace USB manipulation
    println!("[!] Kernel module not found. Falling back to userspace USB (audio may interrupt)...");

    let mut handle = find_minifuse().expect("No MiniFuse device found or permission denied");

    println!("[*] Found {}... applying settings", model.name());

    for (selector, enable, target) in &commands {
        toggle_feature(&mut handle, *selector, *enable);
        println!(
            "[+] {} toggled {}.",
            target,
            if *enable { "ON" } else { "OFF" }
        );
    }

    let _ = handle.reset();

    println!("[*] All commands sent to {}.", model.name());
}

fn detect_model() -> Option<Model> {
    let devices = rusb::devices().ok()?;
    for device in devices.iter() {
        let device_desc = device.device_descriptor().ok()?;
        if device_desc.vendor_id() == VID {
            if let Some(model) = Model::from_pid(device_desc.product_id()) {
                return Some(model);
            }
        }
    }
    None
}

fn find_minifuse() -> Option<DeviceHandle<GlobalContext>> {
    let devices = rusb::devices().ok()?;
    for device in devices.iter() {
        let device_desc = device.device_descriptor().ok()?;
        if device_desc.vendor_id() == VID && Model::from_pid(device_desc.product_id()).is_some() {
            if let Ok(handle) = device.open() {
                return Some(handle);
            }
        }
    }
    None
}

fn toggle_feature(handle: &mut DeviceHandle<GlobalContext>, selector: u16, enable: bool) {
    let _ = handle.set_auto_detach_kernel_driver(true);

    if let Err(e) = handle.claim_interface(0) {
        eprintln!("Warning: Could not claim interface: {}", e);
    }

    let data = if enable { [1, 0] } else { [0, 0] };

    // Control transfer
    handle
        .write_control(0x21, 34, selector, 0, &data, Duration::from_millis(200))
        .expect("Failed to send control command");

    sleep(Duration::from_millis(100));
    let _ = handle.release_interface(0);
}
