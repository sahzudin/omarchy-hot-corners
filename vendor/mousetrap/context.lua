local M = {}

function M.new()
	return {
		config = nil,
		state = nil,
		logger = nil,
		events = nil,
		errors = nil,
	}
end

return M
