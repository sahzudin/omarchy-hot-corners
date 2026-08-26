local M = {}

M.state = {
	runtime = {
		timer = nil,
		running = false,
	},

	monitor = nil,
	zone = "none",

	time = 0,
	triggered = false,

	last_x = nil,
	last_y = nil,

	active_bindings = nil,

	direction_x = 0,
	direction_y = 0,

	motion = {
		cardinal = 5,
		diagonal = 3,
	},

	timer_interval = 16,

	modifiers = {
		super = false,
		shift = false,
		ctrl = false,
		alt = false,
	},

	debug = false,
}

return M
